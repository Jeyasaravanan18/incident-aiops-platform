"""Alert Repository for ingestion, correlation, and lifecycle operations."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
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
