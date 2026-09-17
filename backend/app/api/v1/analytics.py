import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.alert import Alert
from app.models.incident import Incident
from app.models.service import Service, ServiceHealthCheck
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
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * percentile
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(sorted_values[int(k)], 1)
    d0 = sorted_values[int(f)] * (c - k)
    d1 = sorted_values[int(c)] * (k - f)
    return round(d0 + d1, 1)


@router.get("/summary", response_model=AnalyticsSummaryResponse)
async def get_analytics_summary(
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsSummaryResponse:
    cutoff = datetime.now(UTC) - timedelta(days=days)

    # 1. Fetch incidents within window
    inc_stmt = select(Incident).where(Incident.created_at >= cutoff)
    incidents = list(await session.scalars(inc_stmt))

    total_incidents = len(incidents)
    active_incidents = sum(1 for i in incidents if i.resolved_at is None)
    resolved_incidents = sum(1 for i in incidents if i.resolved_at is not None)

    # 2. MTTA Calculation (acknowledged_at - detected_at in minutes)
    mtta_durations = []
    for inc in incidents:
        if inc.acknowledged_at and inc.detected_at:
            diff = (inc.acknowledged_at - inc.detected_at).total_seconds() / 60.0
            if diff >= 0:
                mtta_durations.append(diff)

    mean_mtta = round(sum(mtta_durations) / len(mtta_durations), 1) if mtta_durations else 0.0
    mtta = MTTAMetric(
        mean_minutes=mean_mtta,
        count=len(mtta_durations),
    )

    # 3. MTTR Calculation (resolved_at - detected_at in minutes)
    mttr_durations = []
    for inc in incidents:
        if inc.resolved_at and inc.detected_at:
            diff = (inc.resolved_at - inc.detected_at).total_seconds() / 60.0
            if diff >= 0:
                mttr_durations.append(diff)

    mttr_durations.sort()
    mean_mttr = round(sum(mttr_durations) / len(mttr_durations), 1) if mttr_durations else 0.0
    median_mttr = calculate_percentile(mttr_durations, 0.50)
    p95_mttr = calculate_percentile(mttr_durations, 0.95)

    mttr = MTTRMetric(
        mean_minutes=mean_mttr,
        median_minutes=median_mttr,
        p95_minutes=p95_mttr,
        count=len(mttr_durations),
    )

    # 4. Total Alerts & Ratio
    total_alerts = (
        await session.scalar(select(func.count(Alert.id)).where(Alert.created_at >= cutoff)) or 0
    )
    alert_ratio = round(total_alerts / total_incidents, 2) if total_incidents > 0 else 0.0

    # 5. Severity Breakdown
    sev_counts: dict[str, int] = defaultdict(int)
    for inc in incidents:
        sev_counts[str(inc.severity)] += 1

    severity_breakdown = [
        SeverityCount(
            severity=sev,
            count=count,
            percentage=round((count / total_incidents) * 100.0, 1) if total_incidents > 0 else 0.0,
        )
        for sev, count in sorted(sev_counts.items())
    ]

    # 6. Incidents by Service
    services = list(await session.scalars(select(Service)))
    service_map = {s.id: s.name for s in services}
    service_incidents: dict[UUID, dict[str, int]] = defaultdict(lambda: {"total": 0, "sev1": 0})
    for inc in incidents:
        service_incidents[inc.service_id]["total"] += 1
        if str(inc.severity) == "SEV1":
            service_incidents[inc.service_id]["sev1"] += 1

    incidents_by_service = [
        ServiceIncidentCount(
            service_id=s_id,
            service_name=service_map.get(s_id, "Unknown Service"),
            count=data["total"],
            sev1_count=data["sev1"],
        )
        for s_id, data in service_incidents.items()
    ]
    incidents_by_service.sort(key=lambda x: x.count, reverse=True)

    # 7. Incident Trends (daily buckets over last 14 days)
    trends_map: dict[str, dict[str, int]] = defaultdict(
        lambda: {"count": 0, "sev1": 0, "sev2": 0, "sev3": 0, "sev4": 0}
    )
    for i in range(14):
        d_str = (datetime.now(UTC) - timedelta(days=13 - i)).strftime("%Y-%m-%d")
        _ = trends_map[d_str]  # Initialize date

    for inc in incidents:
        d_str = inc.created_at.strftime("%Y-%m-%d")
        if d_str in trends_map:
            trends_map[d_str]["count"] += 1
            sev_key = str(inc.severity).lower()
            if sev_key in trends_map[d_str]:
                trends_map[d_str][sev_key] += 1

    incident_trends = [
        IncidentTrendPoint(
            date=d_str,
            count=data["count"],
            sev1=data["sev1"],
            sev2=data["sev2"],
            sev3=data["sev3"],
            sev4=data["sev4"],
        )
        for d_str, data in sorted(trends_map.items())
    ]

    # 8. Service Reliability
    service_reliability = []
    for s in services:
        checks_stmt = select(ServiceHealthCheck).where(
            ServiceHealthCheck.service_id == s.id, ServiceHealthCheck.created_at >= cutoff
        )
        checks = list(await session.scalars(checks_stmt))
        total_checks = len(checks)
        uptime = 100.0
        avg_lat = None
        if total_checks > 0:
            up_count = sum(1 for c in checks if c.availability)
            uptime = round((up_count / total_checks) * 100.0, 1)
            valid_lat = [c.response_time_ms for c in checks if c.response_time_ms is not None]
            if valid_lat:
                avg_lat = round(sum(valid_lat) / len(valid_lat), 1)

        service_reliability.append(
            ServiceReliabilityMetric(
                service_id=s.id,
                service_name=s.name,
                uptime_percentage=uptime,
                total_checks=total_checks,
                avg_latency_ms=avg_lat,
            )
        )

    # 9. Recurring Incident Pattern Detection
    pattern_definitions = [
        (
            "DB_CONNECTION_EXHAUSTION",
            "Database connection pool saturation or timeout",
            ["pool", "timeout", "exhaust", "connection"],
        ),
        (
            "HIGH_LATENCY_DEGRADATION",
            "Upstream API response latency or threshold degradation",
            ["latency", "slow", "delay", "degraded"],
        ),
        (
            "5XX_SPIKE",
            "Elevated HTTP 5xx or server internal errors",
            ["5xx", "500", "502", "503", "504", "error rate"],
        ),
        (
            "MEMORY_PRESSURE",
            "High memory usage or garbage collection pauses",
            ["memory", "oom", "leak", "heap"],
        ),
    ]

    recurring_patterns = []
    for key, desc, keywords in pattern_definitions:
        matched_incidents = []
        affected_services = set()
        for inc in incidents:
            text = f"{inc.title} {inc.description or ''}".lower()
            if any(kw in text for kw in keywords):
                matched_incidents.append(inc.id)
                affected_services.add(service_map.get(inc.service_id, "Unknown"))

        if len(matched_incidents) >= 1:
            recurring_patterns.append(
                RecurringPattern(
                    pattern_key=key,
                    description=desc,
                    occurrences=len(matched_incidents),
                    affected_services=list(affected_services),
                    sample_incident_ids=matched_incidents[:5],
                )
            )

    return AnalyticsSummaryResponse(
        total_incidents=total_incidents,
        active_incidents=active_incidents,
        resolved_incidents=resolved_incidents,
        alert_count=total_alerts,
        alert_to_incident_ratio=alert_ratio,
        mtta=mtta,
        mttr=mttr,
        severity_breakdown=severity_breakdown,
        incidents_by_service=incidents_by_service,
        incident_trends=incident_trends,
        service_reliability=service_reliability,
        recurring_patterns=recurring_patterns,
    )
