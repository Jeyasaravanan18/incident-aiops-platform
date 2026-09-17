from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import UserAuth, require_permission
from app.core.database import clean_doc, get_db
from app.core.errors import AppError
from app.schemas.runbook import RunbookCreate, RunbookRead, RunbookUpdate

router = APIRouter(prefix="/runbooks", tags=["runbooks"])


async def _enrich_runbook(doc: dict[str, Any], db: AsyncIOMotorDatabase) -> RunbookRead:
    c = clean_doc(doc)
    s_name = None
    if c.get("service_id"):
        s_doc = await db.services.find_one({"id": str(c["service_id"])})
        if s_doc:
            s_name = s_doc.get("name")

    return RunbookRead(
        id=c["id"],
        service_id=c.get("service_id"),
        service_name=s_name,
        title=c["title"],
        incident_type=c.get("incident_type"),
        body=c.get("body", ""),
        owner_id=c.get("owner_id"),
        created_at=c.get("created_at"),
        updated_at=c.get("updated_at"),
    )


@router.get("", response_model=list[RunbookRead])
async def list_runbooks(
    service_id: UUID | None = Query(default=None),
    incident_type: str | None = Query(default=None),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> list[RunbookRead]:
    query: dict[str, Any] = {}
    if service_id is not None:
        query["service_id"] = str(service_id)
    if incident_type is not None:
        query["incident_type"] = incident_type

    cursor = db.runbooks.find(query).sort("title", 1)
    docs = await cursor.to_list(100)

    service_ids = {str(d.get("service_id")) for d in docs if d.get("service_id")}
    s_map: dict[str, str] = {}
    if service_ids:
        s_docs = await db.services.find({"id": {"$in": list(service_ids)}}).to_list(
            len(service_ids)
        )
        s_map = {str(s["id"]): str(s["name"]) for s in s_docs}

    return [
        RunbookRead(
            id=c["id"],
            service_id=c.get("service_id"),
            service_name=s_map.get(str(c.get("service_id"))),
            title=c["title"],
            incident_type=c.get("incident_type"),
            body=c.get("body", ""),
            owner_id=c.get("owner_id"),
            created_at=c.get("created_at"),
            updated_at=c.get("updated_at"),
        )
        for c in [clean_doc(d) for d in docs]
    ]


@router.post("", response_model=RunbookRead, status_code=201)
async def create_runbook(
    payload: RunbookCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: UserAuth = Depends(require_permission("service:update")),
) -> RunbookRead:
    now = datetime.now(UTC)
    rb_id = str(uuid4())
    doc = {
        "id": rb_id,
        "service_id": str(payload.service_id) if payload.service_id else None,
        "title": payload.title,
        "incident_type": payload.incident_type,
        "body": payload.body,
        "owner_id": str(user.id),
        "created_at": now,
        "updated_at": now,
    }
    await db.runbooks.insert_one(doc)
    return await _enrich_runbook(doc, db)


@router.get("/{runbook_id}", response_model=RunbookRead)
async def get_runbook(
    runbook_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> RunbookRead:
    rb = await db.runbooks.find_one({"id": str(runbook_id)})
    if rb is None:
        raise AppError("RUNBOOK_NOT_FOUND", "Runbook not found", 404)
    return await _enrich_runbook(rb, db)


@router.patch("/{runbook_id}", response_model=RunbookRead)
async def update_runbook(
    runbook_id: UUID,
    payload: RunbookUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: UserAuth = Depends(require_permission("service:update")),
) -> RunbookRead:
    rid = str(runbook_id)
    rb = await db.runbooks.find_one({"id": rid})
    if rb is None:
        raise AppError("RUNBOOK_NOT_FOUND", "Runbook not found", 404)

    now = datetime.now(UTC)
    updates: dict[str, Any] = {"updated_at": now}
    if payload.service_id is not None:
        updates["service_id"] = str(payload.service_id)
    if payload.title is not None:
        updates["title"] = payload.title
    if payload.incident_type is not None:
        updates["incident_type"] = payload.incident_type
    if payload.body is not None:
        updates["body"] = payload.body

    await db.runbooks.update_one({"id": rid}, {"$set": updates})
    updated = await db.runbooks.find_one({"id": rid})
    return await _enrich_runbook(updated, db)  # type: ignore


@router.delete("/{runbook_id}", status_code=204)
async def delete_runbook(
    runbook_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: UserAuth = Depends(require_permission("service:update")),
) -> None:
    rid = str(runbook_id)
    res = await db.runbooks.delete_one({"id": rid})
    if res.deleted_count == 0:
        raise AppError("RUNBOOK_NOT_FOUND", "Runbook not found", 404)
