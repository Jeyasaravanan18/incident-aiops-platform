from time import perf_counter
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.errors import AppError
from app.models.enums import ServiceStatus
from app.models.incident import Incident
from app.models.service import Service, ServiceHealthCheck
from app.models.user import User
from app.schemas.service import (
    ServiceCreate,
    ServiceDetailRead,
    ServiceHealthCheckRead,
    ServiceRead,
    ServiceUpdate,
)
from app.websocket.manager import websocket_manager

router = APIRouter(prefix="/services", tags=["services"])


@router.get("", response_model=list[ServiceRead])
async def list_services(session: AsyncSession = Depends(get_session)) -> list[Service]:
    return list(await session.scalars(select(Service).order_by(Service.name)))


@router.post("", response_model=ServiceRead, status_code=201)
async def create_service(
    payload: ServiceCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("service:create")),
) -> Service:
    existing = await session.scalar(select(Service).where(Service.slug == payload.slug))
    if existing:
        raise AppError("SLUG_ALREADY_EXISTS", f"Service slug '{payload.slug}' already in use", 409)

    service = Service(
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        owner_id=user.id,
        repository=payload.repository,
        environment=payload.environment,
        health_endpoint=str(payload.health_endpoint) if payload.health_endpoint else None,
        criticality=payload.criticality,
    )
    session.add(service)
    await session.commit()
    await session.refresh(service)
    return service


@router.get("/{service_id}", response_model=ServiceDetailRead)
async def get_service(
    service_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ServiceDetailRead:
    service = await session.get(Service, service_id)
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)

    # Active incidents
    active_incidents_count = (
        await session.scalar(
            select(func.count(Incident.id)).where(
                Incident.service_id == service_id,
                Incident.resolved_at.is_(None),
            )
        )
        or 0
    )

    # Recent health checks (last 20)
    h_stmt = (
        select(ServiceHealthCheck)
        .where(ServiceHealthCheck.service_id == service_id)
        .order_by(ServiceHealthCheck.created_at.desc())
        .limit(20)
    )
    recent_checks = list(await session.scalars(h_stmt))

    # Calculate uptime and average latency
    uptime = 100.0
    avg_latency = None
    if recent_checks:
        available_count = sum(1 for c in recent_checks if c.availability)
        uptime = round((available_count / len(recent_checks)) * 100.0, 1)
        valid_latencies = [
            c.response_time_ms for c in recent_checks if c.response_time_ms is not None
        ]
        if valid_latencies:
            avg_latency = round(sum(valid_latencies) / len(valid_latencies), 1)

    return ServiceDetailRead(
        id=service.id,
        name=service.name,
        slug=service.slug,
        description=service.description,
        repository=service.repository,
        environment=service.environment,
        health_endpoint=service.health_endpoint,
        status=service.status,
        criticality=service.criticality,
        created_at=service.created_at,
        updated_at=service.updated_at,
        uptime_percentage=uptime,
        avg_response_time_ms=avg_latency,
        active_incidents_count=active_incidents_count,
        recent_health_checks=[
            ServiceHealthCheckRead(
                id=c.id,
                service_id=c.service_id,
                http_status=c.http_status,
                response_time_ms=c.response_time_ms,
                availability=c.availability,
                error=c.error,
                created_at=c.created_at,
            )
            for c in recent_checks
        ],
    )


@router.patch("/{service_id}", response_model=ServiceRead)
async def update_service(
    service_id: UUID,
    payload: ServiceUpdate,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission("service:update")),
) -> Service:
    service = await session.get(Service, service_id)
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)

    if payload.name is not None:
        service.name = payload.name
    if payload.description is not None:
        service.description = payload.description
    if payload.repository is not None:
        service.repository = payload.repository
    if payload.environment is not None:
        service.environment = payload.environment
    if payload.health_endpoint is not None:
        service.health_endpoint = str(payload.health_endpoint)
    if payload.criticality is not None:
        service.criticality = payload.criticality
    if payload.status is not None:
        service.status = payload.status

    await session.commit()
    await session.refresh(service)
    return service


@router.delete("/{service_id}", status_code=204)
async def delete_service(
    service_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission("service:update")),
) -> None:
    service = await session.get(Service, service_id)
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)
    await session.delete(service)
    await session.commit()


@router.get("/{service_id}/health", response_model=list[ServiceHealthCheckRead])
async def get_service_health(
    service_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[ServiceHealthCheck]:
    return list(
        await session.scalars(
            select(ServiceHealthCheck)
            .where(ServiceHealthCheck.service_id == service_id)
            .order_by(ServiceHealthCheck.created_at.desc())
            .limit(50)
        )
    )


@router.post("/{service_id}/health-check", response_model=ServiceHealthCheckRead)
async def trigger_health_check(
    service_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission("service:update")),
) -> ServiceHealthCheck:
    service = await session.get(Service, service_id)
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)

    if not service.health_endpoint:
        raise AppError("NO_HEALTH_ENDPOINT", "Service has no configured health endpoint", 400)

    start = perf_counter()
    status_code = None
    available = False
    error_msg = None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(service.health_endpoint)
            status_code = resp.status_code
            available = 200 <= status_code < 400
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {str(exc)}"
        available = False

    latency_ms = int((perf_counter() - start) * 1000)

    check = ServiceHealthCheck(
        service_id=service.id,
        http_status=status_code,
        response_time_ms=latency_ms,
        availability=available,
        error=error_msg,
    )
    session.add(check)

    # Update service status accordingly
    if available:
        service.status = ServiceStatus.HEALTHY
    else:
        service.status = (
            ServiceStatus.DEGRADED
            if (status_code and status_code < 500)
            else ServiceStatus.UNHEALTHY
        )

    await session.commit()
    await session.refresh(check)

    await websocket_manager.broadcast(
        f"service:{service.id}",
        {
            "type": "ServiceHealthChanged",
            "service_id": service.id,
            "status": str(service.status),
            "availability": available,
            "latency_ms": latency_ms,
        },
    )
    return check
