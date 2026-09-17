from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import UserAuth, idempotency_key, require_permission
from app.core.database import clean_doc, get_db
from app.core.errors import AppError
from app.domain.idempotency import (
    get_idempotent_response,
    payload_hash,
    store_idempotent_response,
)
from app.domain.incidents import calculate_severity
from app.models.enums import (
    AlertSeverity,
    AlertStatus,
    Criticality,
    IncidentSeverity,
    IncidentStatus,
)
from app.schemas.alert import (
    AlertAcknowledgeRequest,
    AlertCreate,
    AlertRead,
    AlertResolveRequest,
    AlertSuppressRequest,
)
from app.websocket.manager import websocket_manager

router = APIRouter(prefix="/alerts", tags=["alerts"])


async def _enrich_alert_read(alert_doc: dict[str, Any], db: AsyncIOMotorDatabase) -> AlertRead:
    c = clean_doc(alert_doc)
    s_name = None
    if c.get("service_id"):
        s_doc = await db.services.find_one({"id": str(c["service_id"])})
        if s_doc:
            s_name = s_doc.get("name")

    return AlertRead(
        id=c["id"],
        service_id=c["service_id"],
        service_name=s_name,
        incident_id=c.get("incident_id"),
        source=c.get("source", "system"),
        severity=c.get("severity", AlertSeverity.ERROR.value),
        title=c["title"],
        description=c.get("description"),
        fingerprint=c["fingerprint"],
        metadata_json=c.get("metadata_json") or {},
        first_seen=c.get("first_seen", c.get("created_at")),
        last_seen=c.get("last_seen", c.get("created_at")),
        occurrence_count=c.get("occurrence_count", 1),
        status=c.get("status", AlertStatus.OPEN.value),
        created_at=c.get("created_at"),
    )


@router.get("", response_model=list[AlertRead])
async def list_alerts(
    status: AlertStatus | None = Query(default=None),
    severity: AlertSeverity | None = Query(default=None),
    service_id: UUID | None = Query(default=None),
    incident_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> list[AlertRead]:
    query: dict[str, Any] = {}
    if status is not None:
        query["status"] = str(status)
    if severity is not None:
        query["severity"] = str(severity)
    if service_id is not None:
        query["service_id"] = str(service_id)
    if incident_id is not None:
        query["incident_id"] = str(incident_id)

    cursor = db.alerts.find(query).sort("last_seen", -1).skip(offset).limit(limit)
    docs = await cursor.to_list(limit)

    service_ids = {str(d.get("service_id")) for d in docs if d.get("service_id")}
    s_map: dict[str, str] = {}
    if service_ids:
        s_docs = await db.services.find({"id": {"$in": list(service_ids)}}).to_list(
            len(service_ids)
        )
        s_map = {str(s["id"]): str(s["name"]) for s in s_docs}

    return [
        AlertRead(
            id=c["id"],
            service_id=c["service_id"],
            service_name=s_map.get(str(c.get("service_id"))),
            incident_id=c.get("incident_id"),
            source=c.get("source", "system"),
            severity=c.get("severity", AlertSeverity.ERROR.value),
            title=c["title"],
            description=c.get("description"),
            fingerprint=c["fingerprint"],
            metadata_json=c.get("metadata_json") or {},
            first_seen=c.get("first_seen", c.get("created_at")),
            last_seen=c.get("last_seen", c.get("created_at")),
            occurrence_count=c.get("occurrence_count", 1),
            status=c.get("status", AlertStatus.OPEN.value),
            created_at=c.get("created_at"),
        )
        for c in [clean_doc(d) for d in docs]
    ]


@router.post("", response_model=AlertRead, status_code=201)
async def ingest_alert(
    payload: AlertCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    key: str | None = Depends(idempotency_key),
) -> AlertRead:
    request_hash = payload_hash(payload.model_dump())
    idempotent = await get_idempotent_response(db, key, "alert_ingest", request_hash)
    if idempotent is not None:
        existing_alert = await db.alerts.find_one({"id": idempotent["alert_id"]})
        if existing_alert is not None:
            return await _enrich_alert_read(existing_alert, db)

    sid = str(payload.service_id)
    service = await db.services.find_one({"id": sid})
    if service is None:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)

    now = datetime.now(UTC)

    # 1. Check for exact fingerprint deduplication
    existing = await db.alerts.find_one({"fingerprint": payload.fingerprint})
    if existing:
        occ = existing.get("occurrence_count", 1) + 1
        new_st = clean_doc(existing).get("status", AlertStatus.OPEN.value)
        if new_st in (str(AlertStatus.RESOLVED), str(AlertStatus.SUPPRESSED)):
            new_st = str(AlertStatus.OPEN)

        await db.alerts.update_one(
            {"id": existing["id"]},
            {"$set": {"last_seen": now, "occurrence_count": occ, "status": new_st}},
        )

        await store_idempotent_response(
            db,
            key,
            "alert_ingest",
            request_hash,
            {"alert_id": str(existing["id"]), "deduplicated": True},
        )

        await websocket_manager.broadcast(
            "dashboard",
            {
                "type": "AlertDeduplicated",
                "alert_id": existing["id"],
                "fingerprint": existing["fingerprint"],
                "occurrence_count": occ,
            },
        )
        updated = await db.alerts.find_one({"id": existing["id"]})
        return await _enrich_alert_read(updated, db)  # type: ignore

    # 2. Check for alert correlation with an open active incident for the same service
    active_statuses = [
        str(IncidentStatus.DETECTED),
        str(IncidentStatus.TRIGGERED),
        str(IncidentStatus.ACKNOWLEDGED),
        str(IncidentStatus.INVESTIGATING),
        str(IncidentStatus.MITIGATING),
    ]
    active_incident = await db.incidents.find_one(
        {"service_id": sid, "status": {"$in": active_statuses}}
    )

    crit = Criticality(clean_doc(service).get("criticality", Criticality.MEDIUM.value))

    if active_incident is not None:
        alert_id = str(uuid4())
        alert_doc = {
            "id": alert_id,
            "service_id": sid,
            "incident_id": active_incident["id"],
            "source": payload.source,
            "severity": str(payload.severity),
            "title": payload.title,
            "description": payload.description,
            "fingerprint": payload.fingerprint,
            "metadata_json": {**payload.metadata, "idempotency_key": key, "correlated": True},
            "first_seen": now,
            "last_seen": now,
            "occurrence_count": 1,
            "status": AlertStatus.OPEN.value,
            "created_at": now,
        }
        await db.alerts.insert_one(alert_doc)

        new_severity = calculate_severity(payload.severity, crit)
        curr_sev = IncidentSeverity(clean_doc(active_incident).get("severity", IncidentSeverity.SEV3.value))
        if new_severity.value < curr_sev.value:
            await db.incidents.update_one(
                {"id": active_incident["id"]},
                {"$set": {"severity": str(new_severity), "updated_at": now}},
            )

        await db.timeline_events.insert_one(
            {
                "id": str(uuid4()),
                "incident_id": active_incident["id"],
                "actor_id": None,
                "event_type": "AlertCorrelated",
                "message": f"Correlated alert: '{payload.title}' ({payload.severity})",
                "metadata_json": {"alert_id": alert_id, "fingerprint": payload.fingerprint},
                "created_at": now,
            }
        )

        await store_idempotent_response(
            db,
            key,
            "alert_ingest",
            request_hash,
            {"alert_id": alert_id, "incident_id": str(active_incident["id"]), "correlated": True},
        )

        await websocket_manager.broadcast(
            "dashboard",
            {
                "type": "AlertCorrelated",
                "incident_id": active_incident["id"],
                "alert_id": alert_id,
                "service_id": sid,
            },
        )
        await websocket_manager.broadcast(
            f"incident:{active_incident['id']}",
            {"type": "AlertAttached", "incident_id": active_incident["id"], "alert_id": alert_id},
        )
        return await _enrich_alert_read(alert_doc, db)

    # 3. Create a brand new incident for this alert
    incident_id = str(uuid4())
    inc_sev = calculate_severity(payload.severity, crit)
    inc_doc = {
        "id": incident_id,
        "service_id": sid,
        "title": payload.title,
        "description": payload.description,
        "status": IncidentStatus.TRIGGERED.value,
        "severity": str(inc_sev),
        "detected_at": now,
        "acknowledged_at": None,
        "resolved_at": None,
        "closed_at": None,
        "assignee_id": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.incidents.insert_one(inc_doc)

    alert_id = str(uuid4())
    alert_doc = {
        "id": alert_id,
        "service_id": sid,
        "incident_id": incident_id,
        "source": payload.source,
        "severity": str(payload.severity),
        "title": payload.title,
        "description": payload.description,
        "fingerprint": payload.fingerprint,
        "metadata_json": {**payload.metadata, "idempotency_key": key},
        "first_seen": now,
        "last_seen": now,
        "occurrence_count": 1,
        "status": AlertStatus.OPEN.value,
        "created_at": now,
    }
    await db.alerts.insert_one(alert_doc)

    await db.timeline_events.insert_one(
        {
            "id": str(uuid4()),
            "incident_id": incident_id,
            "actor_id": None,
            "event_type": "IncidentCreated",
            "message": f"Incident created from alert fingerprint '{payload.fingerprint}'",
            "metadata_json": {"alert_source": payload.source, "alert_id": alert_id},
            "created_at": now,
        }
    )

    await store_idempotent_response(
        db,
        key,
        "alert_ingest",
        request_hash,
        {"alert_id": alert_id, "incident_id": incident_id, "deduplicated": False},
    )

    await websocket_manager.broadcast(
        "dashboard",
        {"type": "IncidentCreated", "incident_id": incident_id, "alert_id": alert_id},
    )
    return await _enrich_alert_read(alert_doc, db)


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(
    alert_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> AlertRead:
    aid = str(alert_id)
    alert = await db.alerts.find_one({"id": aid})
    if alert is None:
        raise AppError("ALERT_NOT_FOUND", "Alert not found", 404)
    return await _enrich_alert_read(alert, db)


@router.post("/{alert_id}/acknowledge", response_model=AlertRead)
async def acknowledge_alert(
    alert_id: UUID,
    payload: AlertAcknowledgeRequest = AlertAcknowledgeRequest(),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: UserAuth = Depends(require_permission("alert:update")),
) -> AlertRead:
    aid = str(alert_id)
    alert = await db.alerts.find_one({"id": aid})
    if alert is None:
        raise AppError("ALERT_NOT_FOUND", "Alert not found", 404)

    now = datetime.now(UTC)
    await db.alerts.update_one({"id": aid}, {"$set": {"status": str(AlertStatus.ACKNOWLEDGED)}})

    if alert.get("incident_id"):
        await db.timeline_events.insert_one(
            {
                "id": str(uuid4()),
                "incident_id": alert["incident_id"],
                "actor_id": str(user.id),
                "event_type": "AlertAcknowledged",
                "message": f"Alert '{alert['title']}' acknowledged by {user.full_name}",
                "metadata_json": {"alert_id": aid, "reason": payload.reason},
                "created_at": now,
            }
        )

    updated = await db.alerts.find_one({"id": aid})
    return await _enrich_alert_read(updated, db)  # type: ignore


@router.post("/{alert_id}/suppress", response_model=AlertRead)
async def suppress_alert(
    alert_id: UUID,
    payload: AlertSuppressRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: UserAuth = Depends(require_permission("alert:update")),
) -> AlertRead:
    aid = str(alert_id)
    alert = await db.alerts.find_one({"id": aid})
    if alert is None:
        raise AppError("ALERT_NOT_FOUND", "Alert not found", 404)

    now = datetime.now(UTC)
    meta = alert.get("metadata_json") or {}
    meta["suppression"] = {
        "suppressed_by": user.email,
        "reason": payload.reason,
        "until": (now + timedelta(minutes=payload.duration_minutes)).isoformat(),
    }

    await db.alerts.update_one(
        {"id": aid},
        {"$set": {"status": str(AlertStatus.SUPPRESSED), "metadata_json": meta}},
    )

    if alert.get("incident_id"):
        await db.timeline_events.insert_one(
            {
                "id": str(uuid4()),
                "incident_id": alert["incident_id"],
                "actor_id": str(user.id),
                "event_type": "AlertSuppressed",
                "message": f"Alert '{alert['title']}' suppressed for {payload.duration_minutes}m by {user.full_name}: {payload.reason}",
                "metadata_json": {"alert_id": aid, "reason": payload.reason},
                "created_at": now,
            }
        )

    updated = await db.alerts.find_one({"id": aid})
    return await _enrich_alert_read(updated, db)  # type: ignore


@router.post("/{alert_id}/resolve", response_model=AlertRead)
async def resolve_alert(
    alert_id: UUID,
    payload: AlertResolveRequest = AlertResolveRequest(),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: UserAuth = Depends(require_permission("alert:update")),
) -> AlertRead:
    aid = str(alert_id)
    alert = await db.alerts.find_one({"id": aid})
    if alert is None:
        raise AppError("ALERT_NOT_FOUND", "Alert not found", 404)

    now = datetime.now(UTC)
    await db.alerts.update_one({"id": aid}, {"$set": {"status": str(AlertStatus.RESOLVED)}})

    if alert.get("incident_id"):
        await db.timeline_events.insert_one(
            {
                "id": str(uuid4()),
                "incident_id": alert["incident_id"],
                "actor_id": str(user.id),
                "event_type": "AlertResolved",
                "message": f"Alert '{alert['title']}' resolved by {user.full_name}",
                "metadata_json": {"alert_id": aid, "reason": payload.reason},
                "created_at": now,
            }
        )

    updated = await db.alerts.find_one({"id": aid})
    return await _enrich_alert_read(updated, db)  # type: ignore
