from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import UserAuth, current_user, require_permission
from app.core.database import clean_doc, get_db
from app.core.errors import AppError
from app.domain.incidents import (
    transition_timestamp_fields,
    validate_reopen,
    validate_transition,
)
from app.models.enums import IncidentSeverity, IncidentStatus
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


async def _enrich_incident_read(inc_doc: dict[str, Any], db: AsyncIOMotorDatabase) -> IncidentRead:
    clean_inc = clean_doc(inc_doc)
    sid = clean_inc.get("service_id")
    s_name = None
    if sid:
        s_doc = await db.services.find_one({"id": str(sid)})
        if s_doc:
            s_name = s_doc.get("name")

    aid = clean_inc.get("assignee_id")
    a_name = None
    if aid:
        u_doc = await db.users.find_one({"id": str(aid)})
        if u_doc:
            a_name = u_doc.get("full_name")

    return IncidentRead(
        id=clean_inc["id"],
        service_id=clean_inc["service_id"],
        service_name=s_name,
        title=clean_inc["title"],
        description=clean_inc.get("description"),
        status=clean_inc.get("status", "triggered"),
        severity=clean_inc.get("severity", "sev3"),
        detected_at=clean_inc.get("detected_at"),
        acknowledged_at=clean_inc.get("acknowledged_at"),
        resolved_at=clean_inc.get("resolved_at"),
        closed_at=clean_inc.get("closed_at"),
        assignee_id=clean_inc.get("assignee_id"),
        assignee_name=a_name,
        created_at=clean_inc.get("created_at"),
        updated_at=clean_inc.get("updated_at"),
    )


@router.get("", response_model=list[IncidentRead])
async def list_incidents(
    status: IncidentStatus | None = Query(default=None),
    severity: IncidentSeverity | None = Query(default=None),
    service_id: UUID | None = Query(default=None),
    assignee_id: UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> list[IncidentRead]:
    query: dict[str, Any] = {}
    if status is not None:
        query["status"] = str(status)
    if severity is not None:
        query["severity"] = str(severity)
    if service_id is not None:
        query["service_id"] = str(service_id)
    if assignee_id is not None:
        query["assignee_id"] = str(assignee_id)
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
        ]

    cursor = db.incidents.find(query).sort("created_at", -1).skip(offset).limit(limit)
    docs = await cursor.to_list(limit)

    # Pre-fetch services and users mapping for high efficiency
    service_ids = {str(d.get("service_id")) for d in docs if d.get("service_id")}
    assignee_ids = {str(d.get("assignee_id")) for d in docs if d.get("assignee_id")}

    s_map: dict[str, str] = {}
    if service_ids:
        s_docs = await db.services.find({"id": {"$in": list(service_ids)}}).to_list(
            len(service_ids)
        )
        s_map = {str(s.get("id")): str(s.get("name")) for s in s_docs}

    u_map: dict[str, str] = {}
    if assignee_ids:
        u_docs = await db.users.find({"id": {"$in": list(assignee_ids)}}).to_list(len(assignee_ids))
        u_map = {str(u.get("id")): str(u.get("full_name")) for u in u_docs}

    results = []
    for inc in docs:
        c = clean_doc(inc)
        results.append(
            IncidentRead(
                id=c["id"],
                service_id=c["service_id"],
                service_name=s_map.get(str(c.get("service_id"))),
                title=c["title"],
                description=c.get("description"),
                status=c.get("status", "triggered"),
                severity=c.get("severity", "sev3"),
                detected_at=c.get("detected_at"),
                acknowledged_at=c.get("acknowledged_at"),
                resolved_at=c.get("resolved_at"),
                closed_at=c.get("closed_at"),
                assignee_id=c.get("assignee_id"),
                assignee_name=u_map.get(str(c.get("assignee_id"))),
                created_at=c.get("created_at"),
                updated_at=c.get("updated_at"),
            )
        )
    return results


@router.post("", response_model=IncidentRead, status_code=201)
async def create_incident(
    payload: IncidentCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: UserAuth = Depends(require_permission("incident:create")),
) -> IncidentRead:
    sid = str(payload.service_id)
    service = await db.services.find_one({"id": sid})
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)

    now = datetime.now(UTC)
    incident_id = str(uuid4())
    doc = {
        "id": incident_id,
        "service_id": sid,
        "title": payload.title,
        "description": payload.description,
        "status": "triggered",
        "severity": str(payload.severity),
        "detected_at": now,
        "acknowledged_at": None,
        "resolved_at": None,
        "closed_at": None,
        "assignee_id": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.incidents.insert_one(doc)

    ev_doc = {
        "id": str(uuid4()),
        "incident_id": incident_id,
        "actor_id": str(user.id),
        "event_type": "IncidentCreated",
        "message": f"Incident created manually by {user.full_name}",
        "metadata_json": {"created_by": user.email},
        "created_at": now,
    }
    await db.timeline_events.insert_one(ev_doc)

    await websocket_manager.broadcast(
        "dashboard",
        {"type": "IncidentCreated", "incident_id": incident_id, "severity": str(payload.severity)},
    )

    return await _enrich_incident_read(doc, db)


@router.get("/{incident_id}", response_model=IncidentDetailRead)
async def get_incident(
    incident_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> IncidentDetailRead:
    iid = str(incident_id)
    inc = await db.incidents.find_one({"id": iid})
    if inc is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)
    clean_inc = clean_doc(inc)

    s_name = None
    if clean_inc.get("service_id"):
        s_doc = await db.services.find_one({"id": str(clean_inc["service_id"])})
        if s_doc:
            s_name = s_doc.get("name")

    a_name = None
    if clean_inc.get("assignee_id"):
        u_doc = await db.users.find_one({"id": str(clean_inc["assignee_id"])})
        if u_doc:
            a_name = u_doc.get("full_name")

    # Timeline events
    t_docs = await db.timeline_events.find({"incident_id": iid}).sort("created_at", 1).to_list(200)
    actor_ids = {str(t.get("actor_id")) for t in t_docs if t.get("actor_id")}
    actors_map: dict[str, str] = {}
    if actor_ids:
        a_users = await db.users.find({"id": {"$in": list(actor_ids)}}).to_list(len(actor_ids))
        actors_map = {str(u["id"]): str(u["full_name"]) for u in a_users}

    timeline_events = [
        TimelineEventRead(
            id=t["id"],
            incident_id=t["incident_id"],
            actor_id=t.get("actor_id"),
            actor_name=actors_map.get(str(t.get("actor_id"))),
            event_type=t["event_type"],
            message=t["message"],
            metadata_json=t.get("metadata_json") or {},
            created_at=t["created_at"],
        )
        for t in [clean_doc(d) for d in t_docs]
    ]

    # Comments
    c_docs = (
        await db.incident_comments.find({"incident_id": iid}).sort("created_at", 1).to_list(200)
    )
    c_author_ids = {str(c.get("author_id")) for c in c_docs if c.get("author_id")}
    authors_map: dict[str, str] = {}
    if c_author_ids:
        c_users = await db.users.find({"id": {"$in": list(c_author_ids)}}).to_list(
            len(c_author_ids)
        )
        authors_map = {str(u["id"]): str(u["full_name"]) for u in c_users}

    comments = [
        IncidentCommentRead(
            id=c["id"],
            incident_id=c["incident_id"],
            author_id=c["author_id"],
            author_name=authors_map.get(str(c["author_id"])),
            body=c["body"],
            created_at=c["created_at"],
            edited_at=c.get("edited_at"),
        )
        for c in [clean_doc(d) for d in c_docs]
    ]

    alert_count = await db.alerts.count_documents({"incident_id": iid})

    return IncidentDetailRead(
        id=clean_inc["id"],
        service_id=clean_inc["service_id"],
        service_name=s_name,
        title=clean_inc["title"],
        description=clean_inc.get("description"),
        status=clean_inc.get("status", "triggered"),
        severity=clean_inc.get("severity", "sev3"),
        detected_at=clean_inc.get("detected_at"),
        acknowledged_at=clean_inc.get("acknowledged_at"),
        resolved_at=clean_inc.get("resolved_at"),
        closed_at=clean_inc.get("closed_at"),
        assignee_id=clean_inc.get("assignee_id"),
        assignee_name=a_name,
        created_at=clean_inc.get("created_at"),
        updated_at=clean_inc.get("updated_at"),
        timeline_events=timeline_events,
        comments=comments,
        alert_count=alert_count,
    )


@router.patch("/{incident_id}", response_model=IncidentRead)
async def update_incident(
    incident_id: UUID,
    payload: IncidentUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: UserAuth = Depends(require_permission("incident:update")),
) -> IncidentRead:
    iid = str(incident_id)
    incident = await db.incidents.find_one({"id": iid})
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    changes = []
    updates: dict[str, Any] = {}
    if payload.title is not None and payload.title != incident.get("title"):
        changes.append(f"title changed to '{payload.title}'")
        updates["title"] = payload.title

    if payload.description is not None and payload.description != incident.get("description"):
        changes.append("description updated")
        updates["description"] = payload.description

    if payload.severity is not None and str(payload.severity) != str(incident.get("severity")):
        old_sev = incident.get("severity")
        changes.append(f"severity changed from {old_sev} to {payload.severity}")
        updates["severity"] = str(payload.severity)

    if changes:
        updates["updated_at"] = datetime.now(UTC)
        await db.incidents.update_one({"id": iid}, {"$set": updates})

        await db.timeline_events.insert_one(
            {
                "id": str(uuid4()),
                "incident_id": iid,
                "actor_id": str(user.id),
                "event_type": "IncidentUpdated",
                "message": f"Incident updated by {user.full_name}: {', '.join(changes)}",
                "metadata_json": {"updated_by": user.email, "changes": changes},
                "created_at": datetime.now(UTC),
            }
        )

        event = {"type": "IncidentUpdated", "incident_id": iid, "changes": changes}
        await websocket_manager.broadcast("dashboard", event)
        await websocket_manager.broadcast(f"incident:{iid}", event)

    updated_doc = await db.incidents.find_one({"id": iid})
    return await _enrich_incident_read(updated_doc, db)  # type: ignore


@router.post("/{incident_id}/transition", response_model=IncidentRead)
async def transition_incident(
    incident_id: UUID,
    payload: IncidentTransition,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: UserAuth = Depends(require_permission("incident:update")),
) -> IncidentRead:
    iid = str(incident_id)
    incident = await db.incidents.find_one({"id": iid})
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    current_status = IncidentStatus(incident.get("status", "triggered"))
    validate_transition(current_status, payload.status)

    now = datetime.now(UTC)
    updates: dict[str, Any] = {
        "status": str(payload.status),
        "updated_at": now,
    }

    for field, value in transition_timestamp_fields(payload.status).items():
        updates[field] = value

    await db.incidents.update_one({"id": iid}, {"$set": updates})

    msg = f"Status changed from {current_status} to {payload.status} by {user.full_name}"
    if payload.reason:
        msg += f" (Reason: {payload.reason})"

    await db.timeline_events.insert_one(
        {
            "id": str(uuid4()),
            "incident_id": iid,
            "actor_id": str(user.id),
            "event_type": "IncidentStatusChanged",
            "message": msg,
            "metadata_json": {
                "from": str(current_status),
                "to": str(payload.status),
                "reason": payload.reason,
            },
            "created_at": now,
        }
    )

    event = {
        "type": "IncidentStatusChanged",
        "incident_id": iid,
        "from": str(current_status),
        "to": str(payload.status),
    }
    await websocket_manager.broadcast("dashboard", event)
    await websocket_manager.broadcast(f"incident:{iid}", event)

    updated_doc = await db.incidents.find_one({"id": iid})
    return await _enrich_incident_read(updated_doc, db)  # type: ignore


@router.post("/{incident_id}/reopen", response_model=IncidentRead)
async def reopen_incident(
    incident_id: UUID,
    payload: IncidentReopen,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: UserAuth = Depends(require_permission("incident:update")),
) -> IncidentRead:
    iid = str(incident_id)
    incident = await db.incidents.find_one({"id": iid})
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    current_status = IncidentStatus(incident.get("status", "closed"))
    validate_reopen(current_status)

    now = datetime.now(UTC)
    updates = {
        "status": str(IncidentStatus.INVESTIGATING),
        "closed_at": None,
        "resolved_at": None,
        "updated_at": now,
    }
    await db.incidents.update_one({"id": iid}, {"$set": updates})

    await db.timeline_events.insert_one(
        {
            "id": str(uuid4()),
            "incident_id": iid,
            "actor_id": str(user.id),
            "event_type": "IncidentReopened",
            "message": f"Incident reopened from {current_status} by {user.full_name}. Justification: {payload.reason}",
            "metadata_json": {
                "reopened_by": user.email,
                "from": str(current_status),
                "reason": payload.reason,
            },
            "created_at": now,
        }
    )

    event = {
        "type": "IncidentReopened",
        "incident_id": iid,
        "reason": payload.reason,
    }
    await websocket_manager.broadcast("dashboard", event)
    await websocket_manager.broadcast(f"incident:{iid}", event)

    updated_doc = await db.incidents.find_one({"id": iid})
    return await _enrich_incident_read(updated_doc, db)  # type: ignore


@router.post("/{incident_id}/assign", response_model=IncidentRead)
async def assign_incident(
    incident_id: UUID,
    payload: IncidentAssignRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: UserAuth = Depends(require_permission("incident:assign")),
) -> IncidentRead:
    iid = str(incident_id)
    incident = await db.incidents.find_one({"id": iid})
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    target_user = await db.users.find_one({"id": str(payload.assignee_id)})
    if target_user is None or not target_user.get("is_active", True):
        raise AppError("USER_NOT_FOUND", "Target assignee not found or inactive", 404)

    prev_assignee_id = incident.get("assignee_id")
    now = datetime.now(UTC)

    await db.incidents.update_one(
        {"id": iid},
        {"$set": {"assignee_id": str(payload.assignee_id), "updated_at": now}},
    )

    await db.incident_assignments.insert_one(
        {
            "id": str(uuid4()),
            "incident_id": iid,
            "assignee_id": str(payload.assignee_id),
            "assigned_by_id": str(user.id),
            "reason": payload.reason,
            "created_at": now,
        }
    )

    msg = f"Assigned to {target_user.get('full_name')} by {user.full_name}"
    if payload.reason:
        msg += f" (Reason: {payload.reason})"

    await db.timeline_events.insert_one(
        {
            "id": str(uuid4()),
            "incident_id": iid,
            "actor_id": str(user.id),
            "event_type": "IncidentAssigned",
            "message": msg,
            "metadata_json": {
                "previous_assignee_id": str(prev_assignee_id) if prev_assignee_id else None,
                "new_assignee_id": str(payload.assignee_id),
                "reason": payload.reason,
            },
            "created_at": now,
        }
    )

    event = {
        "type": "IncidentAssigned",
        "incident_id": iid,
        "assignee_id": str(payload.assignee_id),
        "assignee_name": target_user.get("full_name"),
    }
    await websocket_manager.broadcast("dashboard", event)
    await websocket_manager.broadcast(f"incident:{iid}", event)

    updated_doc = await db.incidents.find_one({"id": iid})
    return await _enrich_incident_read(updated_doc, db)  # type: ignore


@router.post("/{incident_id}/comments", response_model=IncidentCommentRead, status_code=201)
async def add_comment(
    incident_id: UUID,
    payload: IncidentCommentCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: UserAuth = Depends(current_user),
) -> IncidentCommentRead:
    iid = str(incident_id)
    incident = await db.incidents.find_one({"id": iid})
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    now = datetime.now(UTC)
    cid = str(uuid4())
    comment_doc = {
        "id": cid,
        "incident_id": iid,
        "author_id": str(user.id),
        "body": payload.body,
        "created_at": now,
        "edited_at": None,
    }
    await db.incident_comments.insert_one(comment_doc)

    await db.timeline_events.insert_one(
        {
            "id": str(uuid4()),
            "incident_id": iid,
            "actor_id": str(user.id),
            "event_type": "CommentAdded",
            "message": f"{user.full_name} commented: {payload.body[:100]}...",
            "metadata_json": {"comment_id": cid},
            "created_at": now,
        }
    )

    event = {
        "type": "CommentAdded",
        "incident_id": iid,
        "comment_id": cid,
        "author": user.full_name,
    }
    await websocket_manager.broadcast(f"incident:{iid}", event)

    return IncidentCommentRead(
        id=cid,  # type: ignore
        incident_id=iid,  # type: ignore
        author_id=user.id,  # type: ignore
        author_name=user.full_name,
        body=payload.body,
        created_at=now,
        edited_at=None,
    )


@router.get("/{incident_id}/comments", response_model=list[IncidentCommentRead])
async def list_comments(
    incident_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> list[IncidentCommentRead]:
    iid = str(incident_id)
    c_docs = (
        await db.incident_comments.find({"incident_id": iid}).sort("created_at", 1).to_list(200)
    )
    author_ids = {str(c.get("author_id")) for c in c_docs if c.get("author_id")}
    authors_map: dict[str, str] = {}
    if author_ids:
        users = await db.users.find({"id": {"$in": list(author_ids)}}).to_list(len(author_ids))
        authors_map = {str(u["id"]): str(u["full_name"]) for u in users}

    return [
        IncidentCommentRead(
            id=c["id"],
            incident_id=c["incident_id"],
            author_id=c["author_id"],
            author_name=authors_map.get(str(c.get("author_id"))),
            body=c["body"],
            created_at=c["created_at"],
            edited_at=c.get("edited_at"),
        )
        for c in [clean_doc(d) for d in c_docs]
    ]


@router.get("/{incident_id}/timeline", response_model=list[TimelineEventRead])
async def get_timeline(
    incident_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> list[TimelineEventRead]:
    iid = str(incident_id)
    t_docs = await db.timeline_events.find({"incident_id": iid}).sort("created_at", 1).to_list(200)
    actor_ids = {str(t.get("actor_id")) for t in t_docs if t.get("actor_id")}
    actors_map: dict[str, str] = {}
    if actor_ids:
        users = await db.users.find({"id": {"$in": list(actor_ids)}}).to_list(len(actor_ids))
        actors_map = {str(u["id"]): str(u["full_name"]) for u in users}

    return [
        TimelineEventRead(
            id=t["id"],
            incident_id=t["incident_id"],
            actor_id=t.get("actor_id"),
            actor_name=actors_map.get(str(t.get("actor_id"))),
            event_type=t["event_type"],
            message=t["message"],
            metadata_json=t.get("metadata_json") or {},
            created_at=t["created_at"],
        )
        for t in [clean_doc(d) for d in t_docs]
    ]


@router.get("/{incident_id}/alerts", response_model=list[AlertRead])
async def list_incident_alerts(
    incident_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> list[AlertRead]:
    iid = str(incident_id)
    a_docs = await db.alerts.find({"incident_id": iid}).sort("last_seen", -1).to_list(200)
    service_ids = {str(a.get("service_id")) for a in a_docs if a.get("service_id")}
    s_map: dict[str, str] = {}
    if service_ids:
        s_docs = await db.services.find({"id": {"$in": list(service_ids)}}).to_list(
            len(service_ids)
        )
        s_map = {str(s["id"]): str(s["name"]) for s in s_docs}

    return [
        AlertRead(
            id=a["id"],
            service_id=a["service_id"],
            service_name=s_map.get(str(a.get("service_id"))),
            incident_id=a.get("incident_id"),
            source=a.get("source", "system"),
            severity=a.get("severity", "error"),
            title=a["title"],
            description=a.get("description"),
            fingerprint=a["fingerprint"],
            metadata_json=a.get("metadata_json") or {},
            first_seen=a.get("first_seen", a.get("created_at")),
            last_seen=a.get("last_seen", a.get("created_at")),
            occurrence_count=a.get("occurrence_count", 1),
            status=a.get("status", "firing"),
            created_at=a.get("created_at"),
        )
        for a in [clean_doc(d) for d in a_docs]
    ]
