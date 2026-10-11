"""Incident, Assignment, Comment, and Timeline Repository."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.enums import IncidentSeverity, IncidentStatus
from app.models.incident import Incident, IncidentAssignment, IncidentComment, TimelineEvent


class IncidentRepository:
    @staticmethod
    async def list_incidents(
        session: AsyncSession,
        service_id: UUID | None = None,
        status: IncidentStatus | None = None,
        severity: IncidentSeverity | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Incident]:
        stmt = select(Incident)
        if service_id is not None:
            stmt = stmt.where(Incident.service_id == service_id)
        if status is not None:
            stmt = stmt.where(Incident.status == status)
        if severity is not None:
            stmt = stmt.where(Incident.severity == severity)

        stmt = stmt.order_by(Incident.created_at.desc()).limit(limit).offset(offset)
        result = await session.scalars(stmt)
        return list(result.all())

    @staticmethod
    async def get_by_id(session: AsyncSession, incident_id: UUID) -> Incident | None:
        return await session.get(Incident, incident_id)

    @staticmethod
    async def find_active_for_service(session: AsyncSession, service_id: UUID) -> Incident | None:
        active_statuses = [
            IncidentStatus.DETECTED,
            IncidentStatus.TRIGGERED,
            IncidentStatus.ACKNOWLEDGED,
            IncidentStatus.INVESTIGATING,
            IncidentStatus.MITIGATING,
        ]
        stmt = (
            select(Incident)
            .where(Incident.service_id == service_id)
            .where(Incident.status.in_(active_statuses))
            .order_by(Incident.created_at.desc())
            .limit(1)
        )
        return await session.scalar(stmt)

    @staticmethod
    async def create_incident(session: AsyncSession, **kwargs) -> Incident:
        incident = Incident(**kwargs)
        session.add(incident)
        await session.flush()
        return incident

    @staticmethod
    async def update_incident(session: AsyncSession, incident: Incident, updates: dict) -> Incident:
        for k, v in updates.items():
            if hasattr(incident, k):
                setattr(incident, k, v)
        incident.updated_at = datetime.now(UTC)
        await session.flush()
        return incident

    @staticmethod
    async def add_timeline_event(
        session: AsyncSession,
        incident_id: UUID,
        event_type: str,
        message: str,
        actor_id: UUID | None = None,
        metadata_json: dict | None = None,
    ) -> TimelineEvent:
        event = TimelineEvent(
            incident_id=incident_id,
            actor_id=actor_id,
            event_type=event_type,
            message=message,
            metadata_json=metadata_json or {},
        )
        session.add(event)
        await session.flush()
        return event

    @staticmethod
    async def list_timeline_events(session: AsyncSession, incident_id: UUID) -> list[TimelineEvent]:
        stmt = (
            select(TimelineEvent)
            .where(TimelineEvent.incident_id == incident_id)
            .order_by(TimelineEvent.created_at.asc())
        )
        result = await session.scalars(stmt)
        return list(result.all())

    @staticmethod
    async def add_comment(
        session: AsyncSession, incident_id: UUID, author_id: UUID, body: str
    ) -> IncidentComment:
        comment = IncidentComment(
            incident_id=incident_id,
            author_id=author_id,
            body=body,
        )
        session.add(comment)
        await session.flush()
        return comment

    @staticmethod
    async def list_comments(session: AsyncSession, incident_id: UUID) -> list[IncidentComment]:
        stmt = (
            select(IncidentComment)
            .where(IncidentComment.incident_id == incident_id)
            .order_by(IncidentComment.created_at.asc())
        )
        result = await session.scalars(stmt)
        return list(result.all())

    @staticmethod
    async def assign_incident(
        session: AsyncSession,
        incident_id: UUID,
        assignee_id: UUID,
        assigned_by_id: UUID | None = None,
        reason: str | None = None,
    ) -> IncidentAssignment:
        assignment = IncidentAssignment(
            incident_id=incident_id,
            assignee_id=assignee_id,
            assigned_by_id=assigned_by_id,
            reason=reason,
        )
        session.add(assignment)
        await session.flush()
        return assignment

    @staticmethod
    async def list_incident_alerts(session: AsyncSession, incident_id: UUID) -> list[Alert]:
        stmt = (
            select(Alert).where(Alert.incident_id == incident_id).order_by(Alert.last_seen.desc())
        )
        result = await session.scalars(stmt)
        return list(result.all())

    @staticmethod
    async def count_incident_alerts(session: AsyncSession, incident_id: UUID) -> int:
        stmt = select(func.count(Alert.id)).where(Alert.incident_id == incident_id)
        return (await session.scalar(stmt)) or 0
