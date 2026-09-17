from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, require_permission
from app.core.database import get_session
from app.core.errors import AppError
from app.domain.incidents import (
    transition_timestamp_fields,
    validate_reopen,
    validate_transition,
)
from app.models.alert import Alert
from app.models.enums import IncidentSeverity, IncidentStatus
from app.models.incident import Incident, IncidentAssignment, IncidentComment, TimelineEvent
from app.models.service import Service
from app.models.user import User
from app.schemas.alert import AlertRead
from app.schemas.incident import (
    IncidentAssignRequest,
    IncidentCommentCreate,
    IncidentCommentRead,
    IncidentCreate,
    IncidentDetailRead,
    IncidentRead,
    IncidentReopen,
    IncidentTransition,
    IncidentUpdate,
    TimelineEventRead,
)
from app.websocket.manager import websocket_manager

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentRead])
async def list_incidents(
    status: IncidentStatus | None = Query(default=None),
    severity: IncidentSeverity | None = Query(default=None),
    service_id: UUID | None = Query(default=None),
    assignee_id: UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[IncidentRead]:
    stmt = (
        select(
            Incident,
            Service.name.label("service_name"),
            User.full_name.label("assignee_name"),
        )
        .outerjoin(Service, Incident.service_id == Service.id)
        .outerjoin(User, Incident.assignee_id == User.id)
    )

    if status is not None:
        stmt = stmt.where(Incident.status == status)
    if severity is not None:
        stmt = stmt.where(Incident.severity == severity)
    if service_id is not None:
        stmt = stmt.where(Incident.service_id == service_id)
    if assignee_id is not None:
        stmt = stmt.where(Incident.assignee_id == assignee_id)
    if search:
        term = f"%{search}%"
        stmt = stmt.where(
            or_(
                Incident.title.ilike(term),
                Incident.description.ilike(term),
            )
        )

    stmt = stmt.order_by(Incident.created_at.desc()).offset(offset).limit(limit)
    rows = (await session.execute(stmt)).all()

    results = []
    for inc, s_name, a_name in rows:
        results.append(
            IncidentRead(
                id=inc.id,
                service_id=inc.service_id,
                service_name=s_name,
                title=inc.title,
                description=inc.description,
                status=inc.status,
                severity=inc.severity,
                detected_at=inc.detected_at,
                acknowledged_at=inc.acknowledged_at,
                resolved_at=inc.resolved_at,
                closed_at=inc.closed_at,
                assignee_id=inc.assignee_id,
                assignee_name=a_name,
                created_at=inc.created_at,
                updated_at=inc.updated_at,
            )
        )
    return results


@router.post("", response_model=IncidentRead, status_code=201)
async def create_incident(
    payload: IncidentCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("incident:create")),
) -> IncidentRead:
    service = await session.get(Service, payload.service_id)
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)

    incident = Incident(
        service_id=payload.service_id,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        detected_at=datetime.now(UTC),
    )
    session.add(incident)
    await session.flush()

    session.add(
        TimelineEvent(
            incident_id=incident.id,
            actor_id=user.id,
            event_type="IncidentCreated",
            message=f"Incident created manually by {user.full_name}",
            metadata_json={"created_by": user.email},
        )
    )
    await session.commit()
    await session.refresh(incident)

    await websocket_manager.broadcast(
        "dashboard",
        {"type": "IncidentCreated", "incident_id": incident.id, "severity": str(incident.severity)},
    )

    return IncidentRead(
        id=incident.id,
        service_id=incident.service_id,
        service_name=service.name,
        title=incident.title,
        description=incident.description,
        status=incident.status,
        severity=incident.severity,
        detected_at=incident.detected_at,
        acknowledged_at=incident.acknowledged_at,
        resolved_at=incident.resolved_at,
        closed_at=incident.closed_at,
        assignee_id=incident.assignee_id,
        assignee_name=None,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
    )


@router.get("/{incident_id}", response_model=IncidentDetailRead)
async def get_incident(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> IncidentDetailRead:
    stmt = (
        select(
            Incident,
            Service.name.label("service_name"),
            User.full_name.label("assignee_name"),
        )
        .outerjoin(Service, Incident.service_id == Service.id)
        .outerjoin(User, Incident.assignee_id == User.id)
        .where(Incident.id == incident_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)
    incident, s_name, a_name = row

    # Timeline events with actor name
    t_stmt = (
        select(TimelineEvent, User.full_name.label("actor_name"))
        .outerjoin(User, TimelineEvent.actor_id == User.id)
        .where(TimelineEvent.incident_id == incident_id)
        .order_by(TimelineEvent.created_at.asc())
    )
    t_rows = (await session.execute(t_stmt)).all()
    timeline_events = [
        TimelineEventRead(
            id=ev.id,
            incident_id=ev.incident_id,
            actor_id=ev.actor_id,
            actor_name=act_name,
            event_type=ev.event_type,
            message=ev.message,
            metadata_json=ev.metadata_json,
            created_at=ev.created_at,
        )
        for ev, act_name in t_rows
    ]

    # Comments with author name
    c_stmt = (
        select(IncidentComment, User.full_name.label("author_name"))
        .outerjoin(User, IncidentComment.author_id == User.id)
        .where(IncidentComment.incident_id == incident_id)
        .order_by(IncidentComment.created_at.asc())
    )
    c_rows = (await session.execute(c_stmt)).all()
    comments = [
        IncidentCommentRead(
            id=c.id,
            incident_id=c.incident_id,
            author_id=c.author_id,
            author_name=auth_name,
            body=c.body,
            created_at=c.created_at,
            edited_at=c.edited_at,
        )
        for c, auth_name in c_rows
    ]

    # Alert count
    alert_count = (
        await session.scalar(select(func.count(Alert.id)).where(Alert.incident_id == incident_id))
        or 0
    )

    return IncidentDetailRead(
        id=incident.id,
        service_id=incident.service_id,
        service_name=s_name,
        title=incident.title,
        description=incident.description,
        status=incident.status,
        severity=incident.severity,
        detected_at=incident.detected_at,
        acknowledged_at=incident.acknowledged_at,
        resolved_at=incident.resolved_at,
        closed_at=incident.closed_at,
        assignee_id=incident.assignee_id,
        assignee_name=a_name,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        timeline_events=timeline_events,
        comments=comments,
        alert_count=alert_count,
    )


@router.patch("/{incident_id}", response_model=IncidentRead)
async def update_incident(
    incident_id: UUID,
    payload: IncidentUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("incident:update")),
) -> IncidentRead:
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    changes = []
    if payload.title is not None and payload.title != incident.title:
        changes.append(f"title changed to '{payload.title}'")
        incident.title = payload.title

    if payload.description is not None and payload.description != incident.description:
        changes.append("description updated")
        incident.description = payload.description

    if payload.severity is not None and payload.severity != incident.severity:
        old_sev = incident.severity
        changes.append(f"severity changed from {old_sev} to {payload.severity}")
        incident.severity = payload.severity

    if changes:
        session.add(
            TimelineEvent(
                incident_id=incident.id,
                actor_id=user.id,
                event_type="IncidentUpdated",
                message=f"Incident updated by {user.full_name}: {', '.join(changes)}",
                metadata_json={"updated_by": user.email, "changes": changes},
            )
        )
        await session.commit()
        await session.refresh(incident)

        event = {"type": "IncidentUpdated", "incident_id": incident.id, "changes": changes}
        await websocket_manager.broadcast("dashboard", event)
        await websocket_manager.broadcast(f"incident:{incident.id}", event)

    return await get_incident(incident_id, session)


@router.post("/{incident_id}/transition", response_model=IncidentRead)
async def transition_incident(
    incident_id: UUID,
    payload: IncidentTransition,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("incident:update")),
) -> IncidentRead:
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    validate_transition(incident.status, payload.status)
    old_status = incident.status
    incident.status = payload.status

    for field, value in transition_timestamp_fields(payload.status).items():
        setattr(incident, field, value)

    msg = f"Status changed from {old_status} to {payload.status} by {user.full_name}"
    if payload.reason:
        msg += f" (Reason: {payload.reason})"

    session.add(
        TimelineEvent(
            incident_id=incident.id,
            actor_id=user.id,
            event_type="IncidentStatusChanged",
            message=msg,
            metadata_json={
                "from": str(old_status),
                "to": str(payload.status),
                "reason": payload.reason,
            },
        )
    )
    await session.commit()
    await session.refresh(incident)

    event = {
        "type": "IncidentStatusChanged",
        "incident_id": incident.id,
        "from": str(old_status),
        "to": str(payload.status),
    }
    await websocket_manager.broadcast("dashboard", event)
    await websocket_manager.broadcast(f"incident:{incident.id}", event)

    return await get_incident(incident_id, session)


@router.post("/{incident_id}/reopen", response_model=IncidentRead)
async def reopen_incident(
    incident_id: UUID,
    payload: IncidentReopen,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("incident:update")),
) -> IncidentRead:
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    validate_reopen(incident.status)
    old_status = incident.status
    incident.status = IncidentStatus.INVESTIGATING
    incident.closed_at = None
    incident.resolved_at = None

    session.add(
        TimelineEvent(
            incident_id=incident.id,
            actor_id=user.id,
            event_type="IncidentReopened",
            message=f"Incident reopened from {old_status} by {user.full_name}. Justification: {payload.reason}",
            metadata_json={
                "reopened_by": user.email,
                "from": str(old_status),
                "reason": payload.reason,
            },
        )
    )
    await session.commit()
    await session.refresh(incident)

    event = {
        "type": "IncidentReopened",
        "incident_id": incident.id,
        "reason": payload.reason,
    }
    await websocket_manager.broadcast("dashboard", event)
    await websocket_manager.broadcast(f"incident:{incident.id}", event)

    return await get_incident(incident_id, session)


@router.post("/{incident_id}/assign", response_model=IncidentRead)
async def assign_incident(
    incident_id: UUID,
    payload: IncidentAssignRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("incident:assign")),
) -> IncidentRead:
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    target_user = await session.get(User, payload.assignee_id)
    if target_user is None or not target_user.is_active:
        raise AppError("USER_NOT_FOUND", "Target assignee not found or inactive", 404)

    prev_assignee_id = incident.assignee_id
    incident.assignee_id = target_user.id

    assignment = IncidentAssignment(
        incident_id=incident.id,
        assignee_id=target_user.id,
        assigned_by_id=user.id,
        reason=payload.reason,
    )
    session.add(assignment)

    msg = f"Assigned to {target_user.full_name} by {user.full_name}"
    if payload.reason:
        msg += f" (Reason: {payload.reason})"

    session.add(
        TimelineEvent(
            incident_id=incident.id,
            actor_id=user.id,
            event_type="IncidentAssigned",
            message=msg,
            metadata_json={
                "previous_assignee_id": str(prev_assignee_id) if prev_assignee_id else None,
                "new_assignee_id": str(target_user.id),
                "reason": payload.reason,
            },
        )
    )
    await session.commit()
    await session.refresh(incident)

    event = {
        "type": "IncidentAssigned",
        "incident_id": incident.id,
        "assignee_id": str(target_user.id),
        "assignee_name": target_user.full_name,
    }
    await websocket_manager.broadcast("dashboard", event)
    await websocket_manager.broadcast(f"incident:{incident.id}", event)

    return await get_incident(incident_id, session)


@router.post("/{incident_id}/comments", response_model=IncidentCommentRead, status_code=201)
async def add_comment(
    incident_id: UUID,
    payload: IncidentCommentCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> IncidentCommentRead:
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    comment = IncidentComment(
        incident_id=incident.id,
        author_id=user.id,
        body=payload.body,
    )
    session.add(comment)
    await session.flush()

    session.add(
        TimelineEvent(
            incident_id=incident.id,
            actor_id=user.id,
            event_type="CommentAdded",
            message=f"{user.full_name} commented: {payload.body[:100]}...",
            metadata_json={"comment_id": str(comment.id)},
        )
    )
    await session.commit()
    await session.refresh(comment)

    event = {
        "type": "CommentAdded",
        "incident_id": incident.id,
        "comment_id": str(comment.id),
        "author": user.full_name,
    }
    await websocket_manager.broadcast(f"incident:{incident.id}", event)

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
    stmt = (
        select(IncidentComment, User.full_name.label("author_name"))
        .outerjoin(User, IncidentComment.author_id == User.id)
        .where(IncidentComment.incident_id == incident_id)
        .order_by(IncidentComment.created_at.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        IncidentCommentRead(
            id=c.id,
            incident_id=c.incident_id,
            author_id=c.author_id,
            author_name=auth_name,
            body=c.body,
            created_at=c.created_at,
            edited_at=c.edited_at,
        )
        for c, auth_name in rows
    ]


@router.get("/{incident_id}/timeline", response_model=list[TimelineEventRead])
async def get_timeline(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[TimelineEventRead]:
    stmt = (
        select(TimelineEvent, User.full_name.label("actor_name"))
        .outerjoin(User, TimelineEvent.actor_id == User.id)
        .where(TimelineEvent.incident_id == incident_id)
        .order_by(TimelineEvent.created_at.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        TimelineEventRead(
            id=ev.id,
            incident_id=ev.incident_id,
            actor_id=ev.actor_id,
            actor_name=act_name,
            event_type=ev.event_type,
            message=ev.message,
            metadata_json=ev.metadata_json,
            created_at=ev.created_at,
        )
        for ev, act_name in rows
    ]


@router.get("/{incident_id}/alerts", response_model=list[AlertRead])
async def list_incident_alerts(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[AlertRead]:
    stmt = (
        select(Alert, Service.name.label("service_name"))
        .outerjoin(Service, Alert.service_id == Service.id)
        .where(Alert.incident_id == incident_id)
        .order_by(Alert.last_seen.desc())
    )
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
