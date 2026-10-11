"""Analytics Repository powered strictly by PostgreSQL 16 SQL Expressions.

Replaces in-memory Python calculations with optimized SQL aggregations:
- FILTER clauses for conditional averages
- PERCENTILE_CONT ... WITHIN GROUP for exact P50/P95 latencies
- generate_series + date_trunc for continuous daily buckets (including zeroes)
- LAG() over timeline_events for duration calculation
- GROUP BY ... HAVING for noisy alert aggregation
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class AnalyticsRepository:
    @staticmethod
    async def get_overview_metrics(session: AsyncSession, cutoff: datetime) -> dict[str, Any]:
        """Calculates incident totals and alert ratios in a single aggregate query."""
        stmt = text(
            """
            SELECT
                count(*) AS total_incidents,
                count(*) FILTER (WHERE resolved_at IS NULL) AS active_incidents,
                count(*) FILTER (WHERE resolved_at IS NOT NULL) AS resolved_incidents
            FROM incidents
            WHERE created_at >= :cutoff;
            """
        )
        row = (await session.execute(stmt, {"cutoff": cutoff})).mappings().one()

        alert_count_stmt = text("SELECT count(*) FROM alerts WHERE created_at >= :cutoff;")
        total_alerts = (await session.scalar(alert_count_stmt, {"cutoff": cutoff})) or 0

        tot = row["total_incidents"] or 0
        ratio = round(total_alerts / tot, 2) if tot > 0 else 0.0

        return {
            "total_incidents": tot,
            "active_incidents": row["active_incidents"] or 0,
            "resolved_incidents": row["resolved_incidents"] or 0,
            "alert_count": total_alerts,
            "alert_to_incident_ratio": ratio,
        }

    @staticmethod
    async def get_mtta_metrics(session: AsyncSession, cutoff: datetime) -> dict[str, Any]:
        """Calculates MTTA using SQL AVG with FILTER."""
        stmt = text(
            """
            SELECT
                coalesce(round(avg(EXTRACT(EPOCH FROM (acknowledged_at - detected_at)) / 60.0)::numeric, 1), 0.0) AS mean_minutes,
                count(*) FILTER (WHERE acknowledged_at IS NOT NULL AND detected_at IS NOT NULL AND acknowledged_at >= detected_at) AS count
            FROM incidents
            WHERE created_at >= :cutoff
              AND acknowledged_at IS NOT NULL
              AND detected_at IS NOT NULL
              AND acknowledged_at >= detected_at;
            """
        )
        row = (await session.execute(stmt, {"cutoff": cutoff})).mappings().one()
        return {
            "mean_minutes": float(row["mean_minutes"]),
            "count": int(row["count"]),
        }

    @staticmethod
    async def get_mttr_metrics(session: AsyncSession, cutoff: datetime) -> dict[str, Any]:
        """Calculates MTTR Mean, P50, and P95 using PERCENTILE_CONT ... WITHIN GROUP."""
        stmt = text(
            """
            SELECT
                coalesce(round(avg(EXTRACT(EPOCH FROM (resolved_at - detected_at)) / 60.0)::numeric, 1), 0.0) AS mean_minutes,
                coalesce(round(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (resolved_at - detected_at)) / 60.0)::numeric, 1), 0.0) AS median_minutes,
                coalesce(round(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (resolved_at - detected_at)) / 60.0)::numeric, 1), 0.0) AS p95_minutes,
                count(*) AS count
            FROM incidents
            WHERE created_at >= :cutoff
              AND resolved_at IS NOT NULL
              AND detected_at IS NOT NULL
              AND resolved_at >= detected_at;
            """
        )
        row = (await session.execute(stmt, {"cutoff": cutoff})).mappings().one()
        return {
            "mean_minutes": float(row["mean_minutes"]),
            "median_minutes": float(row["median_minutes"]),
            "p95_minutes": float(row["p95_minutes"]),
            "count": int(row["count"]),
        }

    @staticmethod
    async def get_severity_breakdown(
        session: AsyncSession, cutoff: datetime
    ) -> list[dict[str, Any]]:
        """Calculates severity counts and percentage distributions using SQL window functions."""
        stmt = text(
            """
            WITH sev_counts AS (
                SELECT
                    severity::text AS severity,
                    count(*) AS count
                FROM incidents
                WHERE created_at >= :cutoff
                GROUP BY severity
            )
            SELECT
                severity,
                count,
                coalesce(round((count * 100.0 / nullif(sum(count) over (), 0))::numeric, 1), 0.0) AS percentage
            FROM sev_counts
            ORDER BY severity ASC;
            """
        )
        rows = (await session.execute(stmt, {"cutoff": cutoff})).mappings().all()
        return [
            {
                "severity": r["severity"],
                "count": int(r["count"]),
                "percentage": float(r["percentage"]),
            }
            for r in rows
        ]

    @staticmethod
    async def get_incidents_by_service(
        session: AsyncSession, cutoff: datetime
    ) -> list[dict[str, Any]]:
        """Groups incident volume per service using SQL JOIN and FILTER."""
        stmt = text(
            """
            SELECT
                s.id AS service_id,
                s.name AS service_name,
                count(i.id) AS count,
                count(i.id) FILTER (WHERE i.severity = 'SEV1') AS sev1_count
            FROM services s
            JOIN incidents i ON s.id = i.service_id AND i.created_at >= :cutoff
            GROUP BY s.id, s.name
            ORDER BY count DESC;
            """
        )
        rows = (await session.execute(stmt, {"cutoff": cutoff})).mappings().all()
        return [
            {
                "service_id": r["service_id"],
                "service_name": r["service_name"],
                "count": int(r["count"]),
                "sev1_count": int(r["sev1_count"]),
            }
            for r in rows
        ]

    @staticmethod
    async def get_incident_trends(
        session: AsyncSession, days_count: int = 14
    ) -> list[dict[str, Any]]:
        """Generates continuous daily trends using SQL generate_series, including zero days."""
        stmt = text(
            """
            WITH days AS (
                SELECT generate_series(
                    date_trunc('day', now() - (:days || ' days')::interval),
                    date_trunc('day', now()),
                    '1 day'::interval
                ) AS day
            ),
            counts AS (
                SELECT
                    date_trunc('day', created_at) AS day,
                    count(*) AS count,
                    count(*) FILTER (WHERE severity = 'SEV1') AS sev1,
                    count(*) FILTER (WHERE severity = 'SEV2') AS sev2,
                    count(*) FILTER (WHERE severity = 'SEV3') AS sev3,
                    count(*) FILTER (WHERE severity = 'SEV4') AS sev4
                FROM incidents
                WHERE created_at >= (now() - (:days || ' days')::interval)
                GROUP BY date_trunc('day', created_at)
            )
            SELECT
                to_char(days.day, 'YYYY-MM-DD') AS date,
                coalesce(counts.count, 0) AS count,
                coalesce(counts.sev1, 0) AS sev1,
                coalesce(counts.sev2, 0) AS sev2,
                coalesce(counts.sev3, 0) AS sev3,
                coalesce(counts.sev4, 0) AS sev4
            FROM days
            LEFT JOIN counts ON days.day = counts.day
            ORDER BY days.day ASC;
            """
        )
        rows = (await session.execute(stmt, {"days": days_count - 1})).mappings().all()
        return [
            {
                "date": r["date"],
                "count": int(r["count"]),
                "sev1": int(r["sev1"]),
                "sev2": int(r["sev2"]),
                "sev3": int(r["sev3"]),
                "sev4": int(r["sev4"]),
            }
            for r in rows
        ]

    @staticmethod
    async def get_service_reliability(
        session: AsyncSession, cutoff: datetime
    ) -> list[dict[str, Any]]:
        """Aggregates availability percentage and latency from service_health_checks in SQL."""
        stmt = text(
            """
            SELECT
                s.id AS service_id,
                s.name AS service_name,
                coalesce(count(c.id), 0) AS total_checks,
                coalesce(round(avg(CASE WHEN c.availability THEN 100.0 ELSE 0.0 END)::numeric, 1), 100.0) AS uptime_percentage,
                round(avg(c.response_time_ms) FILTER (WHERE c.response_time_ms IS NOT NULL)::numeric, 1) AS avg_latency_ms
            FROM services s
            LEFT JOIN service_health_checks c ON s.id = c.service_id AND c.created_at >= :cutoff
            GROUP BY s.id, s.name
            ORDER BY s.name ASC;
            """
        )
        rows = (await session.execute(stmt, {"cutoff": cutoff})).mappings().all()
        return [
            {
                "service_id": r["service_id"],
                "service_name": r["service_name"],
                "uptime_percentage": float(r["uptime_percentage"]),
                "total_checks": int(r["total_checks"]),
                "avg_latency_ms": (
                    float(r["avg_latency_ms"]) if r["avg_latency_ms"] is not None else None
                ),
            }
            for r in rows
        ]

    @staticmethod
    async def get_mtta_mttr_by_service_and_severity(
        session: AsyncSession, cutoff: datetime
    ) -> list[dict[str, Any]]:
        """Computes granular MTTA & MTTR per service and severity breakdown."""
        stmt = text(
            """
            SELECT
                s.name AS service_name,
                i.severity::text AS severity,
                round(avg(EXTRACT(EPOCH FROM (i.acknowledged_at - i.detected_at)) / 60.0)
                    FILTER (WHERE i.acknowledged_at IS NOT NULL AND i.detected_at IS NOT NULL)::numeric, 1) AS mtta_minutes,
                round(avg(EXTRACT(EPOCH FROM (i.resolved_at - i.detected_at)) / 60.0)
                    FILTER (WHERE i.resolved_at IS NOT NULL AND i.detected_at IS NOT NULL)::numeric, 1) AS mttr_minutes,
                count(*) AS count
            FROM incidents i
            JOIN services s ON i.service_id = s.id
            WHERE i.created_at >= :cutoff
            GROUP BY s.name, i.severity
            ORDER BY s.name ASC, i.severity ASC;
            """
        )
        rows = (await session.execute(stmt, {"cutoff": cutoff})).mappings().all()
        return [
            {
                "service_name": r["service_name"],
                "severity": r["severity"],
                "mtta_minutes": (
                    float(r["mtta_minutes"]) if r["mtta_minutes"] is not None else 0.0
                ),
                "mttr_minutes": (
                    float(r["mttr_minutes"]) if r["mttr_minutes"] is not None else 0.0
                ),
                "count": int(r["count"]),
            }
            for r in rows
        ]

    @staticmethod
    async def get_time_spent_in_status_lag(
        session: AsyncSession, incident_id: UUID
    ) -> list[dict[str, Any]]:
        """Calculates duration in each incident status using LAG() window function over timeline_events."""
        stmt = text(
            """
            WITH transitions AS (
                SELECT
                    event_type,
                    message,
                    created_at,
                    lag(created_at) OVER (PARTITION BY incident_id ORDER BY created_at ASC) AS prev_timestamp
                FROM timeline_events
                WHERE incident_id = :incident_id
            )
            SELECT
                event_type,
                message,
                created_at,
                coalesce(round(EXTRACT(EPOCH FROM (created_at - prev_timestamp)) / 60.0::numeric, 2), 0.0) AS duration_minutes
            FROM transitions
            ORDER BY created_at ASC;
            """
        )
        rows = (await session.execute(stmt, {"incident_id": incident_id})).mappings().all()
        return [
            {
                "event_type": r["event_type"],
                "message": r["message"],
                "created_at": r["created_at"],
                "duration_minutes": float(r["duration_minutes"]),
            }
            for r in rows
        ]

    @staticmethod
    async def get_top_noisy_alert_sources(
        session: AsyncSession, cutoff: datetime, min_count: int = 1
    ) -> list[dict[str, Any]]:
        """Groups noisy alert sources using SQL GROUP BY, HAVING, and ORDER BY."""
        stmt = text(
            """
            SELECT
                source,
                count(*) AS alert_count,
                coalesce(sum(occurrence_count), 0) AS total_occurrences
            FROM alerts
            WHERE created_at >= :cutoff
            GROUP BY source
            HAVING count(*) >= :min_count
            ORDER BY total_occurrences DESC, alert_count DESC;
            """
        )
        rows = (
            (await session.execute(stmt, {"cutoff": cutoff, "min_count": min_count}))
            .mappings()
            .all()
        )
        return [
            {
                "source": r["source"],
                "alert_count": int(r["alert_count"]),
                "total_occurrences": int(r["total_occurrences"]),
            }
            for r in rows
        ]
