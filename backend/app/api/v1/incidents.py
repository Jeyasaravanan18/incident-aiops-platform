from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UserAuth, current_user, require_permission
from app.core.database import get_session
from app.core.errors import AppError
from app.domain.incidents import (
    calculate_severity,
    transition_timestamp_fields,
    validate_reopen,
    validate_transition,
)
from app.models.enums import (
    AlertSeverity,
    IncidentSeverity,
    IncidentStatus,
)
from app.repositories.incident_repo import IncidentRepository
from app.repositories.service_repo import ServiceRepository
from app.repositories.user_repo import UserRepository
from app.schemas.alert import AlertRead
from app.schemas.incident import (
    IncidentAssignPayload,
    IncidentCommentCreate,
    IncidentCommentRead,
    IncidentCreate,
    IncidentDetailRead,
    IncidentRead,
    IncidentReopenPayload,
    IncidentTransition,
    IncidentUpdate,
    TimelineEventRead,
)
from app.websocket.manager import websocket_manager

router = APIRouter(prefix="/incidents", tags=["incidents"])


async def _enrich_incident_read(session: AsyncSession, inc) -> IncidentRead:
    s_name = None
    if inc.service_id:
        svc = await ServiceRepository.get_by_id(session, inc.service_id)
        if svc:
            s_name = svc.name

    u_name = None
    if inc.assignee_id:
        user = await UserRepository.get_by_id(session, inc.assignee_id)
        if user:
            u_name = user.full_name

    return IncidentRead(
        id=inc.id,
        service_id=inc.service_id,
        service_name=s_name,
        title=inc.title,
        description=inc.description,
        status=inc.status.value if hasattr(inc.status, "value") else str(inc.status),
        severity=inc.severity.value if hasattr(inc.severity, "value") else str(inc.severity),
        detected_at=inc.detected_at,
        acknowledged_at=inc.acknowledged_at,
        resolved_at=inc.resolved_at,
        closed_at=inc.closed_at,
        assignee_id=inc.assignee_id,
        assignee_name=u_name,
        created_at=inc.created_at,
        updated_at=inc.updated_at,
    )


@router.get("", response_model=list[IncidentRead])
async def list_incidents(
    service_id: UUID | None = Query(default=None),
    status: IncidentStatus | None = Query(default=None),
    severity: IncidentSeverity | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[IncidentRead]:
    incidents = await IncidentRepository.list_incidents(
        session=session,
        service_id=service_id,
        status=status,
        severity=severity,
        limit=limit,
        offset=offset,
    )

    # Cache services & users lookup
    service_ids = {i.service_id for i in incidents if i.service_id}
    assignee_ids = {i.assignee_id for i in incidents if i.assignee_id}

    s_map = {}
    for sid in service_ids:
        s = await ServiceRepository.get_by_id(session, sid)
        if s:
            s_map[sid] = s.name

    u_map = {}
    for aid in assignee_ids:
        u = await UserRepository.get_by_id(session, aid)
        if u:
            u_map[aid] = u.full_name

    return [
        IncidentRead(
            id=i.id,
            service_id=i.service_id,
            service_name=s_map.get(i.service_id),
            title=i.title,
            description=i.description,
            status=i.status.value if hasattr(i.status, "value") else str(i.status),
            severity=i.severity.value if hasattr(i.severity, "value") else str(i.severity),
            detected_at=i.detected_at,
            acknowledged_at=i.acknowledged_at,
            resolved_at=i.resolved_at,
            closed_at=i.closed_at,
            assignee_id=i.assignee_id,
            assignee_name=u_map.get(i.assignee_id),
            created_at=i.created_at,
            updated_at=i.updated_at,
        )
        for i in incidents
    ]


@router.post("", response_model=IncidentRead, status_code=201)
async def create_incident(
    payload: IncidentCreate,
    session: AsyncSession = Depends(get_session),
    user: UserAuth = Depends(require_permission("incident:create")),
) -> IncidentRead:
    service = await ServiceRepository.get_by_id(session, payload.service_id)
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)

    now = datetime.now(UTC)
    detected_at = payload.detected_at or now

    if payload.severity is not None:
        severity = (
            IncidentSeverity(payload.severity)
            if isinstance(payload.severity, str)
            else payload.severity
        )
    else:
        severity = calculate_severity(AlertSeverity.CRITICAL, service.criticality)

    incident = await IncidentRepository.create_incident(
        session=session,
        service_id=payload.service_id,
        title=payload.title,
        description=payload.description,
        status=IncidentStatus.TRIGGERED,
        severity=severity,
        detected_at=detected_at,
    )

    await IncidentRepository.add_timeline_event(
        session=session,
        incident_id=incident.id,
        event_type="IncidentDeclared",
        message=f"Incident declared: '{payload.title}' by {user.full_name}",
        actor_id=user.id,
        metadata_json={"severity": severity.value},
    )

    await websocket_manager.broadcast(
        "dashboard",
        {
            "type": "IncidentCreated",
            "incident_id": str(incident.id),
            "service_id": str(payload.service_id),
            "severity": severity.value,
            "title": payload.title,
        },
    )

    return await _enrich_incident_read(session, incident)


@router.get("/{incident_id}", response_model=IncidentDetailRead)
async def get_incident(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> IncidentDetailRead:
    incident = await IncidentRepository.get_by_id(session, incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    s_name = None
    if incident.service_id:
        svc = await ServiceRepository.get_by_id(session, incident.service_id)
        if svc:
            s_name = svc.name

    u_name = None
    if incident.assignee_id:
        u = await UserRepository.get_by_id(session, incident.assignee_id)
        if u:
            u_name = u.full_name

    timeline_events = await IncidentRepository.list_timeline_events(session, incident_id)
    comments = await IncidentRepository.list_comments(session, incident_id)
    alert_count = await IncidentRepository.count_incident_alerts(session, incident_id)

    # Actor names
    actor_ids = {e.actor_id for e in timeline_events if e.actor_id}
    author_ids = {c.author_id for c in comments if c.author_id}
    user_cache = {}
    for uid in actor_ids | author_ids:
        usr = await UserRepository.get_by_id(session, uid)
        if usr:
            user_cache[uid] = usr.full_name

    return IncidentDetailRead(
        id=incident.id,
        service_id=incident.service_id,
        service_name=s_name,
        title=incident.title,
        description=incident.description,
        status=incident.status.value if hasattr(incident.status, "value") else str(incident.status),
        severity=(
            incident.severity.value
            if hasattr(incident.severity, "value")
            else str(incident.severity)
        ),
        detected_at=incident.detected_at,
        acknowledged_at=incident.acknowledged_at,
        resolved_at=incident.resolved_at,
        closed_at=incident.closed_at,
        assignee_id=incident.assignee_id,
        assignee_name=u_name,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        timeline_events=[
            TimelineEventRead(
                id=e.id,
                incident_id=e.incident_id,
                actor_id=e.actor_id,
                actor_name=user_cache.get(e.actor_id),
                event_type=e.event_type,
                message=e.message,
                metadata_json=e.metadata_json or {},
                created_at=e.created_at,
            )
            for e in timeline_events
        ],
        comments=[
            IncidentCommentRead(
                id=c.id,
                incident_id=c.incident_id,
                author_id=c.author_id,
                author_name=user_cache.get(c.author_id),
                body=c.body,
                created_at=c.created_at,
                edited_at=c.edited_at,
            )
            for c in comments
        ],
        alert_count=alert_count,
    )


@router.patch("/{incident_id}", response_model=IncidentRead)
async def update_incident(
    incident_id: UUID,
    payload: IncidentUpdate,
    session: AsyncSession = Depends(get_session),
    _: UserAuth = Depends(require_permission("incident:update")),
) -> IncidentRead:
    incident = await IncidentRepository.get_by_id(session, incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    updates = payload.model_dump(exclude_unset=True)
    if "severity" in updates and updates["severity"] is not None:
        updates["severity"] = (
            IncidentSeverity(updates["severity"])
            if isinstance(updates["severity"], str)
            else updates["severity"]
        )

    updated = await IncidentRepository.update_incident(session, incident, updates)
    return await _enrich_incident_read(session, updated)


@router.post("/{incident_id}/transition", response_model=IncidentRead)
async def transition_incident(
    incident_id: UUID,
    payload: IncidentTransition,
    session: AsyncSession = Depends(get_session),
    user: UserAuth = Depends(require_permission("incident:update")),
) -> IncidentRead:
    incident = await IncidentRepository.get_by_id_for_update(session, incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    current_status = (
        IncidentStatus(incident.status) if isinstance(incident.status, str) else incident.status
    )
    target_status = (
        IncidentStatus(payload.status) if isinstance(payload.status, str) else payload.status
    )

    validate_transition(current_status, target_status)

    updates = {"status": target_status}
    for field, val in transition_timestamp_fields(target_status).items():
        updates[field] = val

    updated = await IncidentRepository.update_incident(session, incident, updates)

    msg = f"Status changed from {current_status.value} to {target_status.value} by {user.full_name}"
    if payload.reason:
        msg += f" (Reason: {payload.reason})"

    await IncidentRepository.add_timeline_event(
        session=session,
        incident_id=incident.id,
        event_type="IncidentStatusChanged",
        message=msg,
        actor_id=user.id,
        metadata_json={
            "from_status": current_status.value,
            "to_status": target_status.value,
            "reason": payload.reason,
        },
    )

    await websocket_manager.broadcast(
        f"incident:{incident_id}",
        {
            "type": "IncidentStatusChanged",
            "incident_id": str(incident_id),
            "status": target_status.value,
        },
    )

    return await _enrich_incident_read(session, updated)


@router.post("/{incident_id}/reopen", response_model=IncidentRead)
async def reopen_incident(
    incident_id: UUID,
    payload: IncidentReopenPayload,
    session: AsyncSession = Depends(get_session),
    user: UserAuth = Depends(require_permission("incident:update")),
) -> IncidentRead:
    incident = await IncidentRepository.get_by_id(session, incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    current_status = (
        IncidentStatus(incident.status) if isinstance(incident.status, str) else incident.status
    )
    validate_reopen(current_status)

    updates = {
        "status": IncidentStatus.TRIGGERED,
        "resolved_at": None,
        "closed_at": None,
    }
    updated = await IncidentRepository.update_incident(session, incident, updates)

    await IncidentRepository.add_timeline_event(
        session=session,
        incident_id=incident.id,
        event_type="IncidentReopened",
        message=f"Incident reopened by {user.full_name}: {payload.reason}",
        actor_id=user.id,
        metadata_json={"reason": payload.reason, "from_status": current_status.value},
    )

    await websocket_manager.broadcast(
        f"incident:{incident_id}",
        {
            "type": "IncidentStatusChanged",
            "incident_id": str(incident_id),
            "status": IncidentStatus.TRIGGERED.value,
        },
    )

    return await _enrich_incident_read(session, updated)


@router.post("/{incident_id}/assign", response_model=IncidentRead)
async def assign_incident(
    incident_id: UUID,
    payload: IncidentAssignPayload,
    session: AsyncSession = Depends(get_session),
    user: UserAuth = Depends(require_permission("incident:assign")),
) -> IncidentRead:
    incident = await IncidentRepository.get_by_id(session, incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    assignee = await UserRepository.get_by_id(session, payload.assignee_id)
    if assignee is None:
        raise AppError("USER_NOT_FOUND", "Assignee user not found", 404)

    updated = await IncidentRepository.update_incident(
        session, incident, {"assignee_id": payload.assignee_id}
    )

    await IncidentRepository.assign_incident(
        session=session,
        incident_id=incident_id,
        assignee_id=payload.assignee_id,
        assigned_by_id=user.id,
        reason=payload.reason,
    )

    msg = f"Assigned to {assignee.full_name} by {user.full_name}"
    if payload.reason:
        msg += f" (Reason: {payload.reason})"

    await IncidentRepository.add_timeline_event(
        session=session,
        incident_id=incident_id,
        event_type="IncidentAssigned",
        message=msg,
        actor_id=user.id,
        metadata_json={"assignee_id": str(payload.assignee_id), "reason": payload.reason},
    )

    await websocket_manager.broadcast(
        f"incident:{incident_id}",
        {
            "type": "IncidentAssigned",
            "incident_id": str(incident_id),
            "assignee_id": str(payload.assignee_id),
            "assignee_name": assignee.full_name,
        },
    )

    return await _enrich_incident_read(session, updated)


@router.post("/{incident_id}/comments", response_model=IncidentCommentRead, status_code=201)
async def add_comment(
    incident_id: UUID,
    payload: IncidentCommentCreate,
    session: AsyncSession = Depends(get_session),
    user: UserAuth = Depends(current_user),
) -> IncidentCommentRead:
    incident = await IncidentRepository.get_by_id(session, incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    comment = await IncidentRepository.add_comment(
        session=session,
        incident_id=incident_id,
        author_id=user.id,
        body=payload.body,
    )

    await IncidentRepository.add_timeline_event(
        session=session,
        incident_id=incident_id,
        event_type="CommentAdded",
        message=f"{user.full_name} commented: '{payload.body[:80]}...'",
        actor_id=user.id,
        metadata_json={"comment_id": str(comment.id)},
    )

    await websocket_manager.broadcast(
        f"incident:{incident_id}",
        {
            "type": "CommentAdded",
            "incident_id": str(incident_id),
            "comment_id": str(comment.id),
            "author_name": user.full_name,
        },
    )

    return IncidentCommentRead(
        id=comment.id,
        incident_id=comment.incident_id,
        author_id=comment.author_id,
        author_name=user.full_name,
        body=comment.body,
        created_at=comment.created_at,
        edited_at=comment.edited_at,
    )


@router.get("/{incident_id}/comments", response_model=list[IncidentCommentRead])
async def list_comments(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[IncidentCommentRead]:
    comments = await IncidentRepository.list_comments(session, incident_id)
    u_cache = {}
    result = []
    for c in comments:
        if c.author_id not in u_cache:
            usr = await UserRepository.get_by_id(session, c.author_id)
            u_cache[c.author_id] = usr.full_name if usr else "Unknown"
        result.append(
            IncidentCommentRead(
                id=c.id,
                incident_id=c.incident_id,
                author_id=c.author_id,
                author_name=u_cache[c.author_id],
                body=c.body,
                created_at=c.created_at,
                edited_at=c.edited_at,
            )
        )
    return result


@router.get("/{incident_id}/timeline", response_model=list[TimelineEventRead])
async def get_timeline(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[TimelineEventRead]:
    events = await IncidentRepository.list_timeline_events(session, incident_id)
    u_cache = {}
    result = []
    for e in events:
        actor_name = None
        if e.actor_id:
            if e.actor_id not in u_cache:
                usr = await UserRepository.get_by_id(session, e.actor_id)
                u_cache[e.actor_id] = usr.full_name if usr else None
            actor_name = u_cache[e.actor_id]
        result.append(
            TimelineEventRead(
                id=e.id,
                incident_id=e.incident_id,
                actor_id=e.actor_id,
                actor_name=actor_name,
                event_type=e.event_type,
                message=e.message,
                metadata_json=e.metadata_json or {},
                created_at=e.created_at,
            )
        )
    return result


@router.get("/{incident_id}/alerts", response_model=list[AlertRead])
async def list_incident_alerts(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[AlertRead]:
    alerts = await IncidentRepository.list_incident_alerts(session, incident_id)
    s_cache = {}
    result = []
    for a in alerts:
        if a.service_id not in s_cache:
            svc = await ServiceRepository.get_by_id(session, a.service_id)
            s_cache[a.service_id] = svc.name if svc else None
        result.append(
            AlertRead(
                id=a.id,
                service_id=a.service_id,
                service_name=s_cache[a.service_id],
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
        )
    return result
