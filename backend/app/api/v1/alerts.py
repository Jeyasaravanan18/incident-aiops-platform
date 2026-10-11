from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UserAuth, idempotency_key, require_permission
from app.core.database import get_session
from app.core.errors import AppError
from app.domain.alerts import compute_alert_fingerprint
from app.domain.idempotency import (
    get_idempotent_response,
    payload_hash,
    store_idempotent_response,
)
from app.domain.incidents import calculate_severity
from app.models.enums import (
    AlertSeverity,
    AlertStatus,
    IncidentSeverity,
    IncidentStatus,
)
from app.repositories.alert_repo import AlertRepository
from app.repositories.incident_repo import IncidentRepository
from app.repositories.service_repo import ServiceRepository
from app.schemas.alert import (
    AlertAcknowledgeRequest,
    AlertCreate,
    AlertRead,
    AlertResolveRequest,
    AlertSuppressRequest,
)
from app.websocket.manager import websocket_manager

router = APIRouter(prefix="/alerts", tags=["alerts"])


async def _enrich_alert(session: AsyncSession, alert) -> AlertRead:
    s_name = None
    if alert.service_id:
        svc = await ServiceRepository.get_by_id(session, alert.service_id)
        if svc:
            s_name = svc.name

    return AlertRead(
        id=alert.id,
        service_id=alert.service_id,
        service_name=s_name,
        incident_id=alert.incident_id,
        source=alert.source,
        severity=alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity),
        title=alert.title,
        description=alert.description,
        fingerprint=alert.fingerprint,
        metadata_json=alert.metadata_json or {},
        first_seen=alert.first_seen,
        last_seen=alert.last_seen,
        occurrence_count=alert.occurrence_count,
        status=alert.status.value if hasattr(alert.status, "value") else str(alert.status),
        created_at=alert.created_at,
    )


@router.get("", response_model=list[AlertRead])
async def list_alerts(
    status: AlertStatus | None = Query(default=None),
    severity: AlertSeverity | None = Query(default=None),
    service_id: UUID | None = Query(default=None),
    incident_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[AlertRead]:
    alerts = await AlertRepository.list_alerts(
        session=session,
        status=status,
        severity=severity,
        service_id=service_id,
        incident_id=incident_id,
        limit=limit,
        offset=offset,
    )
    # Cache service names
    service_ids = {a.service_id for a in alerts if a.service_id}
    svc_map = {}
    for sid in service_ids:
        s = await ServiceRepository.get_by_id(session, sid)
        if s:
            svc_map[sid] = s.name

    return [
        AlertRead(
            id=a.id,
            service_id=a.service_id,
            service_name=svc_map.get(a.service_id),
            incident_id=a.incident_id,
            source=a.source,
            severity=a.severity.value if hasattr(a.severity, "value") else str(a.severity),
            title=a.title,
            description=a.description,
            fingerprint=a.fingerprint,
            metadata_json=a.metadata_json or {},
            first_seen=a.first_seen,
            last_seen=a.last_seen,
            occurrence_count=a.occurrence_count,
            status=a.status.value if hasattr(a.status, "value") else str(a.status),
            created_at=a.created_at,
        )
        for a in alerts
    ]


@router.post("", response_model=AlertRead, status_code=201)
async def ingest_alert(
    payload: AlertCreate,
    session: AsyncSession = Depends(get_session),
    key: str | None = Depends(idempotency_key),
) -> AlertRead:
    request_hash = payload_hash(payload.model_dump())
    idempotent = await get_idempotent_response(session, key, "alert_ingest", request_hash)
    if idempotent is not None:
        cached_id = UUID(str(idempotent["alert_id"]))
        existing_alert = await AlertRepository.get_by_id(session, cached_id)
        if existing_alert is not None:
            return await _enrich_alert(session, existing_alert)

    service = await ServiceRepository.get_by_id(session, payload.service_id)
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)

    now = datetime.now(UTC)

    # 1. Server-side deterministic fingerprinting
    fingerprint = compute_alert_fingerprint(
        service_id=payload.service_id,
        title=payload.title,
        metadata_json=payload.metadata,
    )
    alert_severity = (
        AlertSeverity(payload.severity) if isinstance(payload.severity, str) else payload.severity
    )

    # 2. Acquire transaction advisory lock on service_id to serialize alert storms & prevent duplicate incidents
    await IncidentRepository.acquire_service_advisory_lock(session, payload.service_id)

    # 3. Check for active open incident on the same service or auto-create one for alert storm
    active_incident = await IncidentRepository.find_active_for_service(session, payload.service_id)
    if active_incident is None:
        calc_sev = calculate_severity(alert_severity, service.criticality)
        active_incident = await IncidentRepository.create_incident(
            session=session,
            service_id=payload.service_id,
            title=f"Incident: {payload.title}",
            description=f"Auto-created incident from alert storm ({payload.title})",
            severity=calc_sev,
            status=IncidentStatus.TRIGGERED,
            detected_at=now,
        )
        await IncidentRepository.add_timeline_event(
            session=session,
            incident_id=active_incident.id,
            event_type="IncidentAutoCreated",
            message=f"Incident auto-created from alert storm: '{payload.title}' ({alert_severity.value})",
            actor_id=None,
            metadata_json={"alert_title": payload.title, "severity": alert_severity.value},
        )
    else:
        new_severity = calculate_severity(alert_severity, service.criticality)
        curr_sev = (
            IncidentSeverity(active_incident.severity)
            if isinstance(active_incident.severity, str)
            else active_incident.severity
        )
        sev_rank = {
            IncidentSeverity.SEV4: 4,
            IncidentSeverity.SEV3: 3,
            IncidentSeverity.SEV2: 2,
            IncidentSeverity.SEV1: 1,
        }
        if sev_rank[new_severity] < sev_rank[curr_sev]:
            await IncidentRepository.update_incident(
                session, active_incident, {"severity": new_severity}
            )

    incident_id = active_incident.id

    # 4. Atomic upsert alert (ON CONFLICT DO UPDATE)
    alert, is_inserted = await AlertRepository.upsert_alert(
        session=session,
        service_id=payload.service_id,
        incident_id=incident_id,
        source=payload.source,
        severity=alert_severity,
        title=payload.title,
        description=payload.description,
        fingerprint=fingerprint,
        metadata_json={**payload.metadata, "idempotency_key": key},
    )

    if not is_inserted:
        await store_idempotent_response(
            session,
            key,
            "alert_ingest",
            request_hash,
            {"alert_id": str(alert.id), "deduplicated": True},
        )
        await websocket_manager.broadcast(
            "dashboard",
            {
                "type": "AlertDeduplicated",
                "alert_id": str(alert.id),
                "fingerprint": alert.fingerprint,
                "occurrence_count": alert.occurrence_count,
            },
        )
        return await _enrich_alert(session, alert)

    # Correlate newly inserted alert with timeline event
    await IncidentRepository.add_timeline_event(
        session=session,
        incident_id=active_incident.id,
        event_type="AlertCorrelated",
        message=f"Correlated alert: '{payload.title}' ({alert_severity.value})",
        actor_id=None,
        metadata_json={"alert_id": str(alert.id), "fingerprint": fingerprint},
    )

    await store_idempotent_response(
        session,
        key,
        "alert_ingest",
        request_hash,
        {"alert_id": str(alert.id), "deduplicated": False},
    )

    await websocket_manager.broadcast(
        "dashboard",
        {
            "type": "AlertCreated",
            "alert_id": str(alert.id),
            "service_id": str(payload.service_id),
            "severity": alert_severity.value,
            "title": payload.title,
        },
    )

    return await _enrich_alert(session, alert)


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(
    alert_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> AlertRead:
    alert = await AlertRepository.get_by_id(session, alert_id)
    if alert is None:
        raise AppError("ALERT_NOT_FOUND", "Alert not found", 404)
    return await _enrich_alert(session, alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertRead)
async def acknowledge_alert(
    alert_id: UUID,
    payload: AlertAcknowledgeRequest,
    session: AsyncSession = Depends(get_session),
    user: UserAuth = Depends(require_permission("alert:update")),
) -> AlertRead:
    alert = await AlertRepository.get_by_id(session, alert_id)
    if alert is None:
        raise AppError("ALERT_NOT_FOUND", "Alert not found", 404)

    updated = await AlertRepository.update_status(session, alert, AlertStatus.ACKNOWLEDGED)
    if alert.incident_id:
        await IncidentRepository.add_timeline_event(
            session=session,
            incident_id=alert.incident_id,
            event_type="AlertAcknowledged",
            message=f"Alert '{alert.title}' acknowledged by {user.full_name}",
            actor_id=user.id,
            metadata_json={"alert_id": str(alert.id), "reason": payload.reason},
        )

    await websocket_manager.broadcast(
        "dashboard",
        {"type": "AlertStatusChanged", "alert_id": str(alert.id), "status": "ACKNOWLEDGED"},
    )
    return await _enrich_alert(session, updated)


@router.post("/{alert_id}/suppress", response_model=AlertRead)
async def suppress_alert(
    alert_id: UUID,
    payload: AlertSuppressRequest,
    session: AsyncSession = Depends(get_session),
    user: UserAuth = Depends(require_permission("alert:update")),
) -> AlertRead:
    alert = await AlertRepository.get_by_id(session, alert_id)
    if alert is None:
        raise AppError("ALERT_NOT_FOUND", "Alert not found", 404)

    updated = await AlertRepository.update_status(session, alert, AlertStatus.SUPPRESSED)
    if alert.incident_id:
        await IncidentRepository.add_timeline_event(
            session=session,
            incident_id=alert.incident_id,
            event_type="AlertSuppressed",
            message=f"Alert '{alert.title}' suppressed by {user.full_name} for {payload.duration_minutes}m: {payload.reason}",
            actor_id=user.id,
            metadata_json={"alert_id": str(alert.id), "reason": payload.reason},
        )

    await websocket_manager.broadcast(
        "dashboard",
        {"type": "AlertStatusChanged", "alert_id": str(alert.id), "status": "SUPPRESSED"},
    )
    return await _enrich_alert(session, updated)


@router.post("/{alert_id}/resolve", response_model=AlertRead)
async def resolve_alert(
    alert_id: UUID,
    payload: AlertResolveRequest,
    session: AsyncSession = Depends(get_session),
    user: UserAuth = Depends(require_permission("alert:update")),
) -> AlertRead:
    alert = await AlertRepository.get_by_id(session, alert_id)
    if alert is None:
        raise AppError("ALERT_NOT_FOUND", "Alert not found", 404)

    updated = await AlertRepository.update_status(session, alert, AlertStatus.RESOLVED)
    if alert.incident_id:
        await IncidentRepository.add_timeline_event(
            session=session,
            incident_id=alert.incident_id,
            event_type="AlertResolved",
            message=f"Alert '{alert.title}' resolved by {user.full_name}",
            actor_id=user.id,
            metadata_json={"alert_id": str(alert.id), "reason": payload.reason},
        )

    await websocket_manager.broadcast(
        "dashboard",
        {"type": "AlertStatusChanged", "alert_id": str(alert.id), "status": "RESOLVED"},
    )
    return await _enrich_alert(session, updated)
