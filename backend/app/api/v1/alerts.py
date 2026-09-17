from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import idempotency_key, require_permission
from app.core.database import get_session
from app.core.errors import AppError
from app.domain.idempotency import (
    get_idempotent_response,
    payload_hash,
    store_idempotent_response,
)
from app.domain.incidents import calculate_severity
from app.models.alert import Alert
from app.models.enums import AlertSeverity, AlertStatus, IncidentStatus
from app.models.incident import Incident, TimelineEvent
from app.models.service import Service
from app.models.user import User
from app.schemas.alert import (
    AlertAcknowledgeRequest,
    AlertCreate,
    AlertRead,
    AlertResolveRequest,
    AlertSuppressRequest,
)
from app.websocket.manager import websocket_manager

router = APIRouter(prefix="/alerts", tags=["alerts"])


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
    stmt = select(Alert, Service.name.label("service_name")).outerjoin(
        Service, Alert.service_id == Service.id
    )
    if status is not None:
        stmt = stmt.where(Alert.status == status)
    if severity is not None:
        stmt = stmt.where(Alert.severity == severity)
    if service_id is not None:
        stmt = stmt.where(Alert.service_id == service_id)
    if incident_id is not None:
        stmt = stmt.where(Alert.incident_id == incident_id)

    stmt = stmt.order_by(Alert.last_seen.desc()).offset(offset).limit(limit)
    rows = (await session.execute(stmt)).all()

    return [
        AlertRead(
            id=a.id,
            service_id=a.service_id,
            service_name=s_name,
            incident_id=a.incident_id,
            source=a.source,
            severity=a.severity,
            title=a.title,
            description=a.description,
            fingerprint=a.fingerprint,
            metadata_json=a.metadata_json,
            first_seen=a.first_seen,
            last_seen=a.last_seen,
            occurrence_count=a.occurrence_count,
            status=a.status,
            created_at=a.created_at,
        )
        for a, s_name in rows
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
        existing_alert = await session.get(Alert, idempotent["alert_id"])
        if existing_alert is not None:
            service = await session.get(Service, existing_alert.service_id)
            return AlertRead(
                id=existing_alert.id,
                service_id=existing_alert.service_id,
                service_name=service.name if service else None,
                incident_id=existing_alert.incident_id,
                source=existing_alert.source,
                severity=existing_alert.severity,
                title=existing_alert.title,
                description=existing_alert.description,
                fingerprint=existing_alert.fingerprint,
                metadata_json=existing_alert.metadata_json,
                first_seen=existing_alert.first_seen,
                last_seen=existing_alert.last_seen,
                occurrence_count=existing_alert.occurrence_count,
                status=existing_alert.status,
                created_at=existing_alert.created_at,
            )

    service = await session.get(Service, payload.service_id)
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)

    # 1. Check for exact fingerprint deduplication
    existing = await session.scalar(
        select(Alert)
        .where(Alert.fingerprint == payload.fingerprint)
        .order_by(Alert.created_at.desc())
    )
    if existing:
        existing.last_seen = datetime.now(UTC)
        existing.occurrence_count += 1
        if existing.status in (AlertStatus.RESOLVED, AlertStatus.SUPPRESSED):
            existing.status = AlertStatus.OPEN

        store_idempotent_response(
            session,
            key,
            "alert_ingest",
            request_hash,
            {"alert_id": str(existing.id), "deduplicated": True},
        )
        await session.commit()
        await session.refresh(existing)

        await websocket_manager.broadcast(
            "dashboard",
            {
                "type": "AlertDeduplicated",
                "alert_id": existing.id,
                "fingerprint": existing.fingerprint,
                "occurrence_count": existing.occurrence_count,
            },
        )
        return AlertRead(
            id=existing.id,
            service_id=existing.service_id,
            service_name=service.name,
            incident_id=existing.incident_id,
            source=existing.source,
            severity=existing.severity,
            title=existing.title,
            description=existing.description,
            fingerprint=existing.fingerprint,
            metadata_json=existing.metadata_json,
            first_seen=existing.first_seen,
            last_seen=existing.last_seen,
            occurrence_count=existing.occurrence_count,
            status=existing.status,
            created_at=existing.created_at,
        )

    # 2. Check for alert correlation with an open active incident for the same service
    active_incident = await session.scalar(
        select(Incident)
        .where(
            Incident.service_id == service.id,
            Incident.status.in_(
                [
                    IncidentStatus.DETECTED,
                    IncidentStatus.TRIGGERED,
                    IncidentStatus.ACKNOWLEDGED,
                    IncidentStatus.INVESTIGATING,
                    IncidentStatus.MITIGATING,
                ]
            ),
        )
        .order_by(Incident.created_at.desc())
    )

    if active_incident is not None:
        # Correlate alert to existing active incident
        alert = Alert(
            service_id=service.id,
            incident_id=active_incident.id,
            source=payload.source,
            severity=payload.severity,
            title=payload.title,
            description=payload.description,
            fingerprint=payload.fingerprint,
            metadata_json={**payload.metadata, "idempotency_key": key, "correlated": True},
        )
        session.add(alert)
        await session.flush()

        # Check if severity needs escalation
        new_severity = calculate_severity(payload.severity, service.criticality)
        if (
            new_severity.value < active_incident.severity.value
        ):  # Lower value = higher severity (SEV1 < SEV2)
            active_incident.severity = new_severity

        session.add(
            TimelineEvent(
                incident_id=active_incident.id,
                event_type="AlertCorrelated",
                message=f"Correlated alert: '{payload.title}' ({payload.severity})",
                metadata_json={"alert_id": str(alert.id), "fingerprint": payload.fingerprint},
            )
        )
        store_idempotent_response(
            session,
            key,
            "alert_ingest",
            request_hash,
            {"alert_id": str(alert.id), "incident_id": str(active_incident.id), "correlated": True},
        )
        await session.commit()
        await session.refresh(alert)

        await websocket_manager.broadcast(
            "dashboard",
            {
                "type": "AlertCorrelated",
                "incident_id": active_incident.id,
                "alert_id": alert.id,
                "service_id": service.id,
            },
        )
        await websocket_manager.broadcast(
            f"incident:{active_incident.id}",
            {"type": "AlertAttached", "incident_id": active_incident.id, "alert_id": alert.id},
        )
        return AlertRead(
            id=alert.id,
            service_id=alert.service_id,
            service_name=service.name,
            incident_id=alert.incident_id,
            source=alert.source,
            severity=alert.severity,
            title=alert.title,
            description=alert.description,
            fingerprint=alert.fingerprint,
            metadata_json=alert.metadata_json,
            first_seen=alert.first_seen,
            last_seen=alert.last_seen,
            occurrence_count=alert.occurrence_count,
            status=alert.status,
            created_at=alert.created_at,
        )

    # 3. Create a brand new incident for this alert
    incident = Incident(
        service_id=service.id,
        title=payload.title,
        description=payload.description,
        status=IncidentStatus.TRIGGERED,
        severity=calculate_severity(payload.severity, service.criticality),
        detected_at=datetime.now(UTC),
    )
    session.add(incident)
    await session.flush()

    alert = Alert(
        service_id=service.id,
        incident_id=incident.id,
        source=payload.source,
        severity=payload.severity,
        title=payload.title,
        description=payload.description,
        fingerprint=payload.fingerprint,
        metadata_json={**payload.metadata, "idempotency_key": key},
    )
    session.add(alert)
    await session.flush()

    session.add(
        TimelineEvent(
            incident_id=incident.id,
            event_type="IncidentCreated",
            message=f"Incident created from alert fingerprint '{payload.fingerprint}'",
            metadata_json={"alert_source": payload.source, "alert_id": str(alert.id)},
        )
    )

    store_idempotent_response(
        session,
        key,
        "alert_ingest",
        request_hash,
        {"alert_id": str(alert.id), "incident_id": str(incident.id), "deduplicated": False},
    )
    await session.commit()
    await session.refresh(alert)

    await websocket_manager.broadcast(
        "dashboard",
        {"type": "IncidentCreated", "incident_id": incident.id, "alert_id": alert.id},
    )
    return AlertRead(
        id=alert.id,
        service_id=alert.service_id,
        service_name=service.name,
        incident_id=alert.incident_id,
        source=alert.source,
        severity=alert.severity,
        title=alert.title,
        description=alert.description,
        fingerprint=alert.fingerprint,
        metadata_json=alert.metadata_json,
        first_seen=alert.first_seen,
        last_seen=alert.last_seen,
        occurrence_count=alert.occurrence_count,
        status=alert.status,
        created_at=alert.created_at,
    )


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(
    alert_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> AlertRead:
    stmt = (
        select(Alert, Service.name.label("service_name"))
        .outerjoin(Service, Alert.service_id == Service.id)
        .where(Alert.id == alert_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise AppError("ALERT_NOT_FOUND", "Alert not found", 404)
    alert, s_name = row
    return AlertRead(
        id=alert.id,
        service_id=alert.service_id,
        service_name=s_name,
        incident_id=alert.incident_id,
        source=alert.source,
        severity=alert.severity,
        title=alert.title,
        description=alert.description,
        fingerprint=alert.fingerprint,
        metadata_json=alert.metadata_json,
        first_seen=alert.first_seen,
        last_seen=alert.last_seen,
        occurrence_count=alert.occurrence_count,
        status=alert.status,
        created_at=alert.created_at,
    )


@router.post("/{alert_id}/acknowledge", response_model=AlertRead)
async def acknowledge_alert(
    alert_id: UUID,
    payload: AlertAcknowledgeRequest = AlertAcknowledgeRequest(),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("alert:update")),
) -> AlertRead:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise AppError("ALERT_NOT_FOUND", "Alert not found", 404)

    alert.status = AlertStatus.ACKNOWLEDGED
    if alert.incident_id:
        session.add(
            TimelineEvent(
                incident_id=alert.incident_id,
                actor_id=user.id,
                event_type="AlertAcknowledged",
                message=f"Alert '{alert.title}' acknowledged by {user.full_name}",
                metadata_json={"alert_id": str(alert.id), "reason": payload.reason},
            )
        )
    await session.commit()
    await session.refresh(alert)
    return await get_alert(alert_id, session)


@router.post("/{alert_id}/suppress", response_model=AlertRead)
async def suppress_alert(
    alert_id: UUID,
    payload: AlertSuppressRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("alert:update")),
) -> AlertRead:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise AppError("ALERT_NOT_FOUND", "Alert not found", 404)

    alert.status = AlertStatus.SUPPRESSED
    alert.metadata_json = {
        **alert.metadata_json,
        "suppression": {
            "suppressed_by": user.email,
            "reason": payload.reason,
            "until": (datetime.now(UTC) + timedelta(minutes=payload.duration_minutes)).isoformat(),
        },
    }
    if alert.incident_id:
        session.add(
            TimelineEvent(
                incident_id=alert.incident_id,
                actor_id=user.id,
                event_type="AlertSuppressed",
                message=f"Alert '{alert.title}' suppressed for {payload.duration_minutes}m by {user.full_name}: {payload.reason}",
                metadata_json={"alert_id": str(alert.id), "reason": payload.reason},
            )
        )
    await session.commit()
    await session.refresh(alert)
    return await get_alert(alert_id, session)


@router.post("/{alert_id}/resolve", response_model=AlertRead)
async def resolve_alert(
    alert_id: UUID,
    payload: AlertResolveRequest = AlertResolveRequest(),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("alert:update")),
) -> AlertRead:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise AppError("ALERT_NOT_FOUND", "Alert not found", 404)

    alert.status = AlertStatus.RESOLVED
    if alert.incident_id:
        session.add(
            TimelineEvent(
                incident_id=alert.incident_id,
                actor_id=user.id,
                event_type="AlertResolved",
                message=f"Alert '{alert.title}' resolved by {user.full_name}",
                metadata_json={"alert_id": str(alert.id), "reason": payload.reason},
            )
        )
    await session.commit()
    await session.refresh(alert)
    return await get_alert(alert_id, session)
