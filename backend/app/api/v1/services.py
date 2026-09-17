from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import UserAuth, require_permission
from app.core.database import clean_doc, get_db
from app.core.errors import AppError
from app.models.enums import Criticality, ServiceStatus
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
async def list_services(db: AsyncIOMotorDatabase = Depends(get_db)) -> list[ServiceRead]:
    cursor = db.services.find().sort("name", 1)
    docs = await cursor.to_list(100)
    return [ServiceRead(**clean_doc(d)) for d in docs]  # type: ignore


@router.post("", response_model=ServiceRead, status_code=201)
async def create_service(
    payload: ServiceCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: UserAuth = Depends(require_permission("service:create")),
) -> ServiceRead:
    existing = await db.services.find_one({"slug": payload.slug})
    if existing:
        raise AppError("SLUG_ALREADY_EXISTS", f"Service slug '{payload.slug}' already in use", 409)

    now = datetime.now(UTC)
    service_id = str(uuid4())
    doc = {
        "id": service_id,
        "name": payload.name,
        "slug": payload.slug,
        "description": payload.description,
        "owner_id": str(user.id),
        "repository": payload.repository,
        "environment": payload.environment,
        "health_endpoint": str(payload.health_endpoint) if payload.health_endpoint else None,
        "criticality": str(payload.criticality),
        "status": ServiceStatus.HEALTHY.value,
        "created_at": now,
        "updated_at": now,
    }
    await db.services.insert_one(doc)
    return ServiceRead(**clean_doc(doc))  # type: ignore


@router.get("/{service_id}", response_model=ServiceDetailRead)
async def get_service(
    service_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> ServiceDetailRead:
    sid = str(service_id)
    service = await db.services.find_one({"id": sid})
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)

    active_incidents_count = await db.incidents.count_documents(
        {"service_id": sid, "resolved_at": None}
    )

    checks_cursor = db.health_checks.find({"service_id": sid}).sort("created_at", -1)
    recent_checks_raw = await checks_cursor.to_list(20)
    recent_checks = [clean_doc(c) for c in recent_checks_raw]

    uptime = 100.0
    avg_latency = None
    if recent_checks:
        available_count = sum(1 for c in recent_checks if c.get("availability"))
        uptime = round((available_count / len(recent_checks)) * 100.0, 1)
        valid_latencies = [
            c["response_time_ms"] for c in recent_checks if c.get("response_time_ms") is not None
        ]
        if valid_latencies:
            avg_latency = round(sum(valid_latencies) / len(valid_latencies), 1)

    clean_s = clean_doc(service)
    return ServiceDetailRead(
        id=clean_s["id"],
        name=clean_s["name"],
        slug=clean_s["slug"],
        description=clean_s.get("description"),
        repository=clean_s.get("repository"),
        environment=clean_s.get("environment", "production"),
        health_endpoint=clean_s.get("health_endpoint"),
        status=clean_s.get("status", ServiceStatus.HEALTHY.value),
        criticality=clean_s.get("criticality", Criticality.MEDIUM.value),
        created_at=clean_s["created_at"],
        updated_at=clean_s["updated_at"],
        uptime_percentage=uptime,
        avg_response_time_ms=avg_latency,
        active_incidents_count=active_incidents_count,
        recent_health_checks=[ServiceHealthCheckRead(**c) for c in recent_checks],
    )


@router.patch("/{service_id}", response_model=ServiceRead)
async def update_service(
    service_id: UUID,
    payload: ServiceUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: UserAuth = Depends(require_permission("service:update")),
) -> ServiceRead:
    sid = str(service_id)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        service = await db.services.find_one({"id": sid})
        if not service:
            raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)
        return ServiceRead(**clean_doc(service))  # type: ignore

    if "health_endpoint" in update_data and update_data["health_endpoint"]:
        update_data["health_endpoint"] = str(update_data["health_endpoint"])
    if "status" in update_data and update_data["status"]:
        update_data["status"] = str(update_data["status"])
    if "criticality" in update_data and update_data["criticality"]:
        update_data["criticality"] = str(update_data["criticality"])

    update_data["updated_at"] = datetime.now(UTC)
    await db.services.update_one({"id": sid}, {"$set": update_data})
    service = await db.services.find_one({"id": sid})
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)
    return ServiceRead(**clean_doc(service))  # type: ignore


@router.delete("/{service_id}", status_code=204)
async def delete_service(
    service_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: UserAuth = Depends(require_permission("service:update")),
) -> None:
    sid = str(service_id)
    res = await db.services.delete_one({"id": sid})
    if res.deleted_count == 0:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)


@router.get("/{service_id}/health", response_model=list[ServiceHealthCheckRead])
async def get_service_health(
    service_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> list[ServiceHealthCheckRead]:
    sid = str(service_id)
    checks = await db.health_checks.find({"service_id": sid}).sort("created_at", -1).to_list(50)
    return [ServiceHealthCheckRead(**clean_doc(c)) for c in checks]  # type: ignore


@router.post("/{service_id}/health-check", response_model=ServiceHealthCheckRead)
async def trigger_health_check(
    service_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: UserAuth = Depends(require_permission("service:update")),
) -> ServiceHealthCheckRead:
    sid = str(service_id)
    service = await db.services.find_one({"id": sid})
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)

    health_endpoint = service.get("health_endpoint")
    if not health_endpoint:
        raise AppError("NO_HEALTH_ENDPOINT", "Service has no configured health endpoint", 400)

    start = perf_counter()
    status_code = None
    available = False
    error_msg = None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(health_endpoint)
            status_code = resp.status_code
            available = 200 <= status_code < 400
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {str(exc)}"
        available = False

    latency_ms = int((perf_counter() - start) * 1000)
    now = datetime.now(UTC)
    check_id = str(uuid4())

    check_doc = {
        "id": check_id,
        "service_id": sid,
        "http_status": status_code,
        "response_time_ms": latency_ms,
        "availability": available,
        "error": error_msg,
        "created_at": now,
    }
    await db.health_checks.insert_one(check_doc)

    new_status = (
        ServiceStatus.HEALTHY
        if available
        else (
            ServiceStatus.DEGRADED
            if (status_code and status_code < 500)
            else ServiceStatus.DOWN
        )
    )

    await db.services.update_one(
        {"id": sid},
        {"$set": {"status": str(new_status), "updated_at": now}},
    )

    await websocket_manager.broadcast(
        f"service:{sid}",
        {
            "type": "ServiceHealthChanged",
            "service_id": sid,
            "status": str(new_status),
            "availability": available,
            "latency_ms": latency_ms,
        },
    )
    return ServiceHealthCheckRead(**clean_doc(check_doc))  # type: ignore
