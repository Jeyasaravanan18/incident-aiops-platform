import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.enums import AlertSeverity, AlertStatus


class AlertRepository:
    @staticmethod
    async def list_alerts(
        session: AsyncSession,
        status: AlertStatus | None = None,
        severity: AlertSeverity | None = None,
        service_id: UUID | None = None,
        incident_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Alert]:
        stmt = select(Alert)
        if status is not None:
            stmt = stmt.where(Alert.status == status)
        if severity is not None:
            stmt = stmt.where(Alert.severity == severity)
        if service_id is not None:
            stmt = stmt.where(Alert.service_id == service_id)
        if incident_id is not None:
            stmt = stmt.where(Alert.incident_id == incident_id)

        stmt = stmt.order_by(Alert.last_seen.desc()).limit(limit).offset(offset)
        result = await session.scalars(stmt)
        return list(result.all())

    @staticmethod
    async def get_by_id(session: AsyncSession, alert_id: UUID) -> Alert | None:
        return await session.get(Alert, alert_id)

    @staticmethod
    async def get_by_fingerprint(
        session: AsyncSession, fingerprint: str, status: AlertStatus | None = None
    ) -> Alert | None:
        stmt = select(Alert).where(Alert.fingerprint == fingerprint)
        if status is not None:
            stmt = stmt.where(Alert.status == status)
        return await session.scalar(stmt)

    @staticmethod
    async def upsert_alert(
        session: AsyncSession,
        service_id: UUID,
        incident_id: UUID | None,
        source: str,
        severity: AlertSeverity,
        title: str,
        description: str | None,
        fingerprint: str,
        metadata_json: dict,
    ) -> tuple[Alert, bool]:
        """Atomic INSERT ... ON CONFLICT (fingerprint) DO UPDATE for race-condition-free ingestion."""
        now = datetime.now(UTC)
        stmt = text(
            """
            INSERT INTO alerts (
                id, service_id, incident_id, source, severity, title, description,
                fingerprint, metadata_json, first_seen, last_seen, first_seen_at, last_seen_at,
                occurrence_count, status, created_at, updated_at
            )
            VALUES (
                :id, :service_id, :incident_id, :source, CAST(:severity AS alertseverity), :title, :description,
                :fingerprint, CAST(:metadata_json AS jsonb), :now, :now, :now, :now,
                1, CAST('OPEN' AS alertstatus), :now, :now
            )
            ON CONFLICT (fingerprint) DO UPDATE SET
                occurrence_count = alerts.occurrence_count + 1,
                last_seen = EXCLUDED.last_seen,
                last_seen_at = EXCLUDED.last_seen_at,
                incident_id = coalesce(alerts.incident_id, EXCLUDED.incident_id),
                status = CASE
                    WHEN alerts.status IN ('RESOLVED', 'SUPPRESSED') THEN CAST('OPEN' AS alertstatus)
                    ELSE alerts.status
                END,
                updated_at = EXCLUDED.updated_at
            RETURNING id, occurrence_count, (xmax = 0) AS is_inserted;
            """
        )
        row = (
            (
                await session.execute(
                    stmt,
                    {
                        "id": uuid4(),
                        "service_id": service_id,
                        "incident_id": incident_id,
                        "source": source,
                        "severity": severity.value if hasattr(severity, "value") else str(severity),
                        "title": title,
                        "description": description,
                        "fingerprint": fingerprint,
                        "metadata_json": json.dumps(metadata_json),
                        "now": now,
                    },
                )
            )
            .mappings()
            .one()
        )

        alert_id = row["id"]
        is_inserted = bool(row["is_inserted"])
        alert = await session.get(Alert, alert_id)
        return alert, is_inserted

    @staticmethod
    async def create_alert(session: AsyncSession, **kwargs) -> Alert:
        alert = Alert(**kwargs)
        session.add(alert)
        await session.flush()
        return alert

    @staticmethod
    async def increment_occurrence(
        session: AsyncSession, alert: Alert, new_status: AlertStatus = AlertStatus.OPEN
    ) -> Alert:
        now = datetime.now(UTC)
        alert.occurrence_count += 1
        alert.last_seen = now
        alert.last_seen_at = now
        alert.status = new_status
        await session.flush()
        return alert

    @staticmethod
    async def update_status(session: AsyncSession, alert: Alert, status: AlertStatus) -> Alert:
        now = datetime.now(UTC)
        alert.status = status
        alert.last_seen = now
        alert.last_seen_at = now
        await session.flush()
        return alert
