from time import perf_counter
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UserAuth, require_permission
from app.core.database import get_session
from app.core.errors import AppError
from app.models.enums import Criticality, ServiceStatus
from app.repositories.service_repo import ServiceRepository
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
async def list_services(
    session: AsyncSession = Depends(get_session),
) -> list[ServiceRead]:
    services = await ServiceRepository.list_services(session)
    result = []
    for s in services:
        active_incidents = await ServiceRepository.get_active_incident_count(session, s.id)
        checks = await ServiceRepository.list_health_checks(session, s.id, limit=20)
        uptime = 100.0
        avg_lat = None
        if checks:
            up_count = sum(1 for c in checks if c.availability)
            uptime = round((up_count / len(checks)) * 100.0, 1)
            valid_lat = [c.response_time_ms for c in checks if c.response_time_ms is not None]
            if valid_lat:
                avg_lat = round(sum(valid_lat) / len(valid_lat), 1)

        result.append(
            ServiceRead(
                id=s.id,
                name=s.name,
                slug=s.slug,
                description=s.description,
                repository=s.repository,
                environment=s.environment,
                health_endpoint=s.health_endpoint,
                status=s.status.value if hasattr(s.status, "value") else str(s.status),
                criticality=(
                    s.criticality.value if hasattr(s.criticality, "value") else str(s.criticality)
                ),
                created_at=s.created_at,
                updated_at=s.updated_at,
                uptime_percentage=uptime,
                avg_response_time_ms=avg_lat,
                active_incidents_count=active_incidents,
            )
        )
    return result


@router.post("", response_model=ServiceRead, status_code=201)
async def create_service(
    payload: ServiceCreate,
    session: AsyncSession = Depends(get_session),
    user: UserAuth = Depends(require_permission("service:create")),
) -> ServiceRead:
    existing = await ServiceRepository.get_by_slug(session, payload.slug)
    if existing:
        raise AppError("SLUG_ALREADY_EXISTS", f"Service slug '{payload.slug}' already in use", 409)

    service = await ServiceRepository.create_service(
        session=session,
        name=payload.name,
        slug=payload.slug.strip().lower(),
        description=payload.description,
        owner_id=user.id,
        repository=payload.repository,
        environment=payload.environment,
        health_endpoint=str(payload.health_endpoint) if payload.health_endpoint else None,
        criticality=(
            Criticality(payload.criticality)
            if isinstance(payload.criticality, str)
            else payload.criticality
        ),
        status=ServiceStatus.HEALTHY,
    )

    return ServiceRead(
        id=service.id,
        name=service.name,
        slug=service.slug,
        description=service.description,
        repository=service.repository,
        environment=service.environment,
        health_endpoint=service.health_endpoint,
        status=service.status.value if hasattr(service.status, "value") else str(service.status),
        criticality=(
            service.criticality.value
            if hasattr(service.criticality, "value")
            else str(service.criticality)
        ),
        created_at=service.created_at,
        updated_at=service.updated_at,
        uptime_percentage=100.0,
        active_incidents_count=0,
    )


@router.get("/{service_id}", response_model=ServiceDetailRead)
async def get_service(
    service_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ServiceDetailRead:
    service = await ServiceRepository.get_by_id(session, service_id)
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)

    active_incidents_count = await ServiceRepository.get_active_incident_count(session, service_id)
    recent_checks = await ServiceRepository.list_health_checks(session, service_id, limit=20)

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
        status=service.status.value if hasattr(service.status, "value") else str(service.status),
        criticality=(
            service.criticality.value
            if hasattr(service.criticality, "value")
            else str(service.criticality)
        ),
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
    _: UserAuth = Depends(require_permission("service:update")),
) -> ServiceRead:
    service = await ServiceRepository.get_by_id(session, service_id)
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)

    updates = payload.model_dump(exclude_unset=True)
    if "health_endpoint" in updates and updates["health_endpoint"] is not None:
        updates["health_endpoint"] = str(updates["health_endpoint"])
    if "criticality" in updates and updates["criticality"] is not None:
        updates["criticality"] = Criticality(updates["criticality"])

    updated = await ServiceRepository.update_service(session, service, updates)
    return ServiceRead(
        id=updated.id,
        name=updated.name,
        slug=updated.slug,
        description=updated.description,
        repository=updated.repository,
        environment=updated.environment,
        health_endpoint=updated.health_endpoint,
        status=updated.status.value if hasattr(updated.status, "value") else str(updated.status),
        criticality=(
            updated.criticality.value
            if hasattr(updated.criticality, "value")
            else str(updated.criticality)
        ),
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.delete("/{service_id}", status_code=204)
async def delete_service(
    service_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: UserAuth = Depends(require_permission("service:update")),
) -> None:
    service = await ServiceRepository.get_by_id(session, service_id)
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)
    await ServiceRepository.delete_service(session, service)


@router.get("/{service_id}/health", response_model=list[ServiceHealthCheckRead])
async def get_service_health(
    service_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[ServiceHealthCheckRead]:
    service = await ServiceRepository.get_by_id(session, service_id)
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)

    checks = await ServiceRepository.list_health_checks(session, service_id, limit=50)
    return [
        ServiceHealthCheckRead(
            id=c.id,
            service_id=c.service_id,
            http_status=c.http_status,
            response_time_ms=c.response_time_ms,
            availability=c.availability,
            error=c.error,
            created_at=c.created_at,
        )
        for c in checks
    ]


@router.post("/{service_id}/health-check", response_model=ServiceHealthCheckRead)
async def trigger_health_check(
    service_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: UserAuth = Depends(require_permission("service:update")),
) -> ServiceHealthCheckRead:
    service = await ServiceRepository.get_by_id(session, service_id)
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)

    if not service.health_endpoint:
        raise AppError(
            "HEALTH_ENDPOINT_NOT_CONFIGURED",
            f"Service '{service.name}' has no health_endpoint configured",
            400,
        )

    start = perf_counter()
    status_code = None
    available = False
    error_msg = None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(str(service.health_endpoint))
            status_code = resp.status_code
            available = 200 <= status_code < 400
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {str(exc)}"
        available = False

    latency_ms = int((perf_counter() - start) * 1000)

    check = await ServiceRepository.record_health_check(
        session=session,
        service_id=service_id,
        http_status=status_code,
        response_time_ms=latency_ms,
        availability=available,
        error=error_msg,
    )

    new_status = (
        ServiceStatus.HEALTHY
        if available
        else (ServiceStatus.DEGRADED if (status_code and status_code < 500) else ServiceStatus.DOWN)
    )
    await ServiceRepository.update_service(session, service, {"status": new_status})

    await websocket_manager.broadcast(
        f"service:{service_id}",
        {
            "type": "HealthCheckPerformed",
            "service_id": str(service_id),
            "availability": available,
            "latency_ms": latency_ms,
            "status": new_status.value,
        },
    )

    return ServiceHealthCheckRead(
        id=check.id,
        service_id=check.service_id,
        http_status=check.http_status,
        response_time_ms=check.response_time_ms,
        availability=check.availability,
        error=check.error,
        created_at=check.created_at,
    )
