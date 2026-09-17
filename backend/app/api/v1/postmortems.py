from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import UserAuth, require_permission
from app.core.database import clean_doc, get_db
from app.core.errors import AppError
from app.schemas.postmortem import PostmortemCreate, PostmortemRead, PostmortemUpdate

router = APIRouter(prefix="/postmortems", tags=["postmortems"])


async def _enrich_postmortem(doc: dict[str, Any], db: AsyncIOMotorDatabase) -> PostmortemRead:
    c = clean_doc(doc)
    inc_title = None
    if c.get("incident_id"):
        inc = await db.incidents.find_one({"id": str(c["incident_id"])})
        if inc:
            inc_title = inc.get("title")

    return PostmortemRead(
        id=c["id"],
        incident_id=c["incident_id"],
        incident_title=inc_title,
        summary=c.get("summary", ""),
        impact=c.get("impact", ""),
        timeline=c.get("timeline", ""),
        root_cause=c.get("root_cause", ""),
        contributing_factors=c.get("contributing_factors", ""),
        resolution=c.get("resolution", ""),
        preventive_actions=c.get("preventive_actions", ""),
        lessons_learned=c.get("lessons_learned", ""),
        owner_id=c.get("owner_id"),
        status=c.get("status", "DRAFT"),
        created_at=c.get("created_at"),
        updated_at=c.get("updated_at"),
    )


@router.get("", response_model=list[PostmortemRead])
async def list_postmortems(
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> list[PostmortemRead]:
    cursor = db.postmortems.find().sort("created_at", -1)
    docs = await cursor.to_list(100)

    inc_ids = {str(d.get("incident_id")) for d in docs if d.get("incident_id")}
    inc_map: dict[str, str] = {}
    if inc_ids:
        inc_docs = await db.incidents.find({"id": {"$in": list(inc_ids)}}).to_list(len(inc_ids))
        inc_map = {str(i["id"]): str(i["title"]) for i in inc_docs}

    return [
        PostmortemRead(
            id=c["id"],
            incident_id=c["incident_id"],
            incident_title=inc_map.get(str(c.get("incident_id"))),
            summary=c.get("summary", ""),
            impact=c.get("impact", ""),
            timeline=c.get("timeline", ""),
            root_cause=c.get("root_cause", ""),
            contributing_factors=c.get("contributing_factors", ""),
            resolution=c.get("resolution", ""),
            preventive_actions=c.get("preventive_actions", ""),
            lessons_learned=c.get("lessons_learned", ""),
            owner_id=c.get("owner_id"),
            status=c.get("status", "DRAFT"),
            created_at=c.get("created_at"),
            updated_at=c.get("updated_at"),
        )
        for c in [clean_doc(d) for d in docs]
    ]


@router.post("", response_model=PostmortemRead, status_code=201)
async def create_postmortem(
    payload: PostmortemCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: UserAuth = Depends(require_permission("postmortem:create")),
) -> PostmortemRead:
    iid = str(payload.incident_id)
    incident = await db.incidents.find_one({"id": iid})
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    existing = await db.postmortems.find_one({"incident_id": iid})
    if existing:
        raise AppError(
            "POSTMORTEM_ALREADY_EXISTS", "Postmortem already exists for this incident", 409
        )

    now = datetime.now(UTC)
    pm_id = str(uuid4())
    doc = {
        "id": pm_id,
        "incident_id": iid,
        "summary": payload.summary,
        "impact": payload.impact,
        "timeline": payload.timeline,
        "root_cause": payload.root_cause,
        "contributing_factors": payload.contributing_factors,
        "resolution": payload.resolution,
        "preventive_actions": payload.preventive_actions,
        "lessons_learned": payload.lessons_learned,
        "owner_id": str(user.id),
        "status": "DRAFT",
        "created_at": now,
        "updated_at": now,
    }
    await db.postmortems.insert_one(doc)

    await db.timeline_events.insert_one(
        {
            "id": str(uuid4()),
            "incident_id": iid,
            "actor_id": str(user.id),
            "event_type": "PostmortemCreated",
            "message": f"Postmortem drafted by {user.full_name}",
            "metadata_json": {"postmortem_id": pm_id},
            "created_at": now,
        }
    )

    return await _enrich_postmortem(doc, db)


@router.get("/{postmortem_id}", response_model=PostmortemRead)
async def get_postmortem(
    postmortem_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> PostmortemRead:
    pm = await db.postmortems.find_one({"id": str(postmortem_id)})
    if pm is None:
        raise AppError("POSTMORTEM_NOT_FOUND", "Postmortem not found", 404)
    return await _enrich_postmortem(pm, db)


@router.get("/by-incident/{incident_id}", response_model=PostmortemRead | None)
async def get_postmortem_by_incident(
    incident_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> PostmortemRead | None:
    pm = await db.postmortems.find_one({"incident_id": str(incident_id)})
    if pm is None:
        return None
    return await _enrich_postmortem(pm, db)


@router.patch("/{postmortem_id}", response_model=PostmortemRead)
async def update_postmortem(
    postmortem_id: UUID,
    payload: PostmortemUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: UserAuth = Depends(require_permission("postmortem:create")),
) -> PostmortemRead:
    pid = str(postmortem_id)
    pm = await db.postmortems.find_one({"id": pid})
    if pm is None:
        raise AppError("POSTMORTEM_NOT_FOUND", "Postmortem not found", 404)

    now = datetime.now(UTC)
    updates = payload.model_dump(exclude_unset=True)
    updates["updated_at"] = now

    await db.postmortems.update_one({"id": pid}, {"$set": updates})

    if payload.status == "APPROVED":
        await db.timeline_events.insert_one(
            {
                "id": str(uuid4()),
                "incident_id": pm["incident_id"],
                "actor_id": str(user.id),
                "event_type": "PostmortemApproved",
                "message": f"Postmortem approved by {user.full_name}",
                "metadata_json": {"postmortem_id": pid},
                "created_at": now,
            }
        )

    updated_pm = await db.postmortems.find_one({"id": pid})
    return await _enrich_postmortem(updated_pm, db)  # type: ignore
