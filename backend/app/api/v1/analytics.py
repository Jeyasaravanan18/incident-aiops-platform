from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.repositories.analytics_repo import AnalyticsRepository
from app.schemas.analytics import (
    AnalyticsSummaryResponse,
    IncidentTrendPoint,
    MTTAMetric,
    MTTRMetric,
    RecurringPattern,
    ServiceIncidentCount,
    ServiceReliabilityMetric,
    SeverityCount,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def calculate_percentile(sorted_values: list[float], percentile: float) -> float:
    """Helper for calculating statistical percentiles."""
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * percentile
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return round(sorted_values[f], 1)
    d0 = sorted_values[f] * (c - k)
    d1 = sorted_values[c] * (k - f)
    return round(d0 + d1, 1)


@router.get("/summary", response_model=AnalyticsSummaryResponse)
async def get_analytics_summary(
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsSummaryResponse:
    cutoff = datetime.now(UTC) - timedelta(days=days)

    # 1. Total & Ratio via SQL aggregate
    overview = await AnalyticsRepository.get_overview_metrics(session, cutoff)

    # 2. MTTA via SQL AVG with FILTER
    mtta_data = await AnalyticsRepository.get_mtta_metrics(session, cutoff)
    mtta = MTTAMetric(
        mean_minutes=mtta_data["mean_minutes"],
        count=mtta_data["count"],
    )

    # 3. MTTR Mean, Median, P95 via SQL PERCENTILE_CONT ... WITHIN GROUP
    mttr_data = await AnalyticsRepository.get_mttr_metrics(session, cutoff)
    mttr = MTTRMetric(
        mean_minutes=mttr_data["mean_minutes"],
        median_minutes=mttr_data["median_minutes"],
        p95_minutes=mttr_data["p95_minutes"],
        count=mttr_data["count"],
    )

    # 4. Severity Breakdown via SQL window functions
    sev_rows = await AnalyticsRepository.get_severity_breakdown(session, cutoff)
    severity_breakdown = [
        SeverityCount(
            severity=r["severity"],
            count=r["count"],
            percentage=r["percentage"],
        )
        for r in sev_rows
    ]

    # 5. Incidents by Service via SQL JOIN & FILTER
    svc_rows = await AnalyticsRepository.get_incidents_by_service(session, cutoff)
    incidents_by_service = [
        ServiceIncidentCount(
            service_id=r["service_id"],
            service_name=r["service_name"],
            count=r["count"],
            sev1_count=r["sev1_count"],
        )
        for r in svc_rows
    ]

    # 6. Incident Trends via SQL generate_series
    trend_rows = await AnalyticsRepository.get_incident_trends(session, days_count=14)
    incident_trends = [
        IncidentTrendPoint(
            date=r["date"],
            count=r["count"],
            sev1=r["sev1"],
            sev2=r["sev2"],
            sev3=r["sev3"],
            sev4=r["sev4"],
        )
        for r in trend_rows
    ]

    # 7. Service Reliability via SQL aggregates
    rel_rows = await AnalyticsRepository.get_service_reliability(session, cutoff)
    service_reliability = [
        ServiceReliabilityMetric(
            service_id=r["service_id"],
            service_name=r["service_name"],
            uptime_percentage=r["uptime_percentage"],
            total_checks=r["total_checks"],
            avg_latency_ms=r["avg_latency_ms"],
        )
        for r in rel_rows
    ]

    # 8. Recurring Patterns via SQL ILIKE query
    patterns_def = [
        (
            "DB_CONNECTION_EXHAUSTION",
            "Database connection pool saturation or timeout",
            "%pool%",
        ),
        (
            "HIGH_LATENCY_DEGRADATION",
            "Upstream API response latency or threshold degradation",
            "%latency%",
        ),
        (
            "5XX_SPIKE",
            "Elevated HTTP 5xx or server internal errors",
            "%5xx%",
        ),
        (
            "MEMORY_PRESSURE",
            "High memory usage or garbage collection pauses",
            "%memory%",
        ),
    ]

    recurring_patterns = []
    pattern_stmt = text(
        """
        SELECT i.id, coalesce(s.name, 'Unknown') AS service_name
        FROM incidents i
        LEFT JOIN services s ON i.service_id = s.id
        WHERE i.created_at >= :cutoff
          AND (i.title ILIKE :pattern OR i.description ILIKE :pattern)
        LIMIT 10;
        """
    )
    for p_key, p_desc, pattern_kw in patterns_def:
        matches = (
            (await session.execute(pattern_stmt, {"cutoff": cutoff, "pattern": pattern_kw}))
            .mappings()
            .all()
        )
        if matches:
            aff_services = list({r["service_name"] for r in matches})
            inc_ids = [r["id"] for r in matches[:5]]
            recurring_patterns.append(
                RecurringPattern(
                    pattern_key=p_key,
                    description=p_desc,
                    occurrences=len(matches),
                    affected_services=aff_services,
                    sample_incident_ids=inc_ids,
                )
            )

    return AnalyticsSummaryResponse(
        total_incidents=overview["total_incidents"],
        active_incidents=overview["active_incidents"],
        resolved_incidents=overview["resolved_incidents"],
        alert_count=overview["alert_count"],
        alert_to_incident_ratio=overview["alert_to_incident_ratio"],
        mtta=mtta,
        mttr=mttr,
        severity_breakdown=severity_breakdown,
        incidents_by_service=incidents_by_service,
        incident_trends=incident_trends,
        service_reliability=service_reliability,
        recurring_patterns=recurring_patterns,
    )


@router.get("/breakdown")
async def get_mtta_mttr_breakdown(
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """MTTA and MTTR per service and per severity calculated using SQL AVG with FILTER."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    return await AnalyticsRepository.get_mtta_mttr_by_service_and_severity(session, cutoff)


@router.get("/incidents/{incident_id}/status-durations")
async def get_incident_status_durations(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Calculates time spent in each status transition using SQL LAG() over timeline_events."""
    return await AnalyticsRepository.get_time_spent_in_status_lag(session, incident_id)


@router.get("/noisy-alerts")
async def get_noisy_alerts(
    days: int = Query(default=30, ge=1, le=365),
    min_count: int = Query(default=1, ge=1),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Top noisy alert sources identified using SQL GROUP BY, HAVING, and ORDER BY."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    return await AnalyticsRepository.get_top_noisy_alert_sources(
        session, cutoff, min_count=min_count
    )
