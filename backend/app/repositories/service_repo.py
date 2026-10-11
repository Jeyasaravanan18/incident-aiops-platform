"""Service Catalog and Health Check Repository."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import IncidentStatus
from app.models.incident import Incident
from app.models.service import Service, ServiceHealthCheck


class ServiceRepository:
    @staticmethod
    async def list_services(session: AsyncSession) -> list[Service]:
        stmt = select(Service).order_by(Service.name.asc())
        result = await session.scalars(stmt)
        return list(result.all())

    @staticmethod
    async def get_by_id(session: AsyncSession, service_id: UUID) -> Service | None:
        return await session.get(Service, service_id)

    @staticmethod
    async def get_by_slug(session: AsyncSession, slug: str) -> Service | None:
        stmt = select(Service).where(Service.slug == slug.strip().lower())
        return await session.scalar(stmt)

    @staticmethod
    async def get_by_name(session: AsyncSession, name: str) -> Service | None:
        stmt = select(Service).where(func.lower(Service.name) == name.strip().lower())
        return await session.scalar(stmt)

    @staticmethod
    async def create_service(session: AsyncSession, **kwargs) -> Service:
        service = Service(**kwargs)
        session.add(service)
        await session.flush()
        return service

    @staticmethod
    async def update_service(session: AsyncSession, service: Service, updates: dict) -> Service:
        for k, v in updates.items():
            if hasattr(service, k):
                setattr(service, k, v)
        await session.flush()
        return service

    @staticmethod
    async def delete_service(session: AsyncSession, service: Service) -> None:
        await session.delete(service)
        await session.flush()

    @staticmethod
    async def record_health_check(
        session: AsyncSession,
        service_id: UUID,
        http_status: int | None,
        response_time_ms: int | None,
        availability: bool,
        error: str | None = None,
    ) -> ServiceHealthCheck:
        check = ServiceHealthCheck(
            service_id=service_id,
            http_status=http_status,
            response_time_ms=response_time_ms,
            availability=availability,
            error=error,
        )
        session.add(check)
        await session.flush()
        return check

    @staticmethod
    async def list_health_checks(
        session: AsyncSession, service_id: UUID, limit: int = 50
    ) -> list[ServiceHealthCheck]:
        stmt = (
            select(ServiceHealthCheck)
            .where(ServiceHealthCheck.service_id == service_id)
            .order_by(ServiceHealthCheck.created_at.desc())
            .limit(limit)
        )
        result = await session.scalars(stmt)
        return list(result.all())

    @staticmethod
    async def get_active_incident_count(session: AsyncSession, service_id: UUID) -> int:
        active_statuses = [
            IncidentStatus.DETECTED,
            IncidentStatus.TRIGGERED,
            IncidentStatus.ACKNOWLEDGED,
            IncidentStatus.INVESTIGATING,
            IncidentStatus.MITIGATING,
        ]
        stmt = (
            select(func.count(Incident.id))
            .where(Incident.service_id == service_id)
            .where(Incident.status.in_(active_statuses))
        )
        return (await session.scalar(stmt)) or 0
