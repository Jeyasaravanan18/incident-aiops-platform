from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UserAuth, require_permission
from app.core.database import get_session
from app.core.errors import AppError
from app.models.postmortem import Postmortem
from app.repositories.incident_repo import IncidentRepository
from app.repositories.postmortem_repo import PostmortemRepository
from app.schemas.postmortem import PostmortemCreate, PostmortemRead, PostmortemUpdate

router = APIRouter(prefix="/postmortems", tags=["postmortems"])


async def _enrich_postmortem(pm: Postmortem, session: AsyncSession) -> PostmortemRead:
    inc_title = None
    if pm.incident_id:
        inc = await IncidentRepository.get_by_id(session, pm.incident_id)
        if inc:
            inc_title = inc.title

    return PostmortemRead(
        id=pm.id,
        incident_id=pm.incident_id,
        incident_title=inc_title,
        summary=pm.summary or "",
        impact=pm.impact or "",
        timeline=pm.timeline or "",
        root_cause=pm.root_cause or "",
        contributing_factors=pm.contributing_factors or "",
        resolution=pm.resolution or "",
        preventive_actions=pm.preventive_actions or "",
        lessons_learned=pm.lessons_learned or "",
        owner_id=pm.owner_id,
        status=pm.status or "DRAFT",
        created_at=pm.created_at,
        updated_at=pm.updated_at,
    )


@router.get("", response_model=list[PostmortemRead])
async def list_postmortems(
    session: AsyncSession = Depends(get_session),
) -> list[PostmortemRead]:
    pms = await PostmortemRepository.list_postmortems(session, limit=100)

    inc_ids = {pm.incident_id for pm in pms if pm.incident_id}
    inc_map: dict[UUID, str] = {}
    for iid in inc_ids:
        inc = await IncidentRepository.get_by_id(session, iid)
        if inc:
            inc_map[iid] = inc.title

    return [
        PostmortemRead(
            id=pm.id,
            incident_id=pm.incident_id,
            incident_title=inc_map.get(pm.incident_id),
            summary=pm.summary or "",
            impact=pm.impact or "",
            timeline=pm.timeline or "",
            root_cause=pm.root_cause or "",
            contributing_factors=pm.contributing_factors or "",
            resolution=pm.resolution or "",
            preventive_actions=pm.preventive_actions or "",
            lessons_learned=pm.lessons_learned or "",
            owner_id=pm.owner_id,
            status=pm.status or "DRAFT",
            created_at=pm.created_at,
            updated_at=pm.updated_at,
        )
        for pm in pms
    ]


@router.post("", response_model=PostmortemRead, status_code=201)
async def create_postmortem(
    payload: PostmortemCreate,
    session: AsyncSession = Depends(get_session),
    user: UserAuth = Depends(require_permission("postmortem:create")),
) -> PostmortemRead:
    incident = await IncidentRepository.get_by_id(session, payload.incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    existing = await PostmortemRepository.get_by_incident_id(session, payload.incident_id)
    if existing:
        raise AppError(
            "POSTMORTEM_ALREADY_EXISTS", "Postmortem already exists for this incident", 409
        )

    pm = await PostmortemRepository.create_postmortem(
        session,
        incident_id=payload.incident_id,
        summary=payload.summary,
        impact=payload.impact,
        timeline=payload.timeline,
        root_cause=payload.root_cause,
        contributing_factors=payload.contributing_factors,
        resolution=payload.resolution,
        preventive_actions=payload.preventive_actions,
        lessons_learned=payload.lessons_learned,
        owner_id=user.id,
        status="DRAFT",
    )

    await IncidentRepository.add_timeline_event(
        session,
        incident_id=payload.incident_id,
        actor_id=user.id,
        event_type="PostmortemCreated",
        message=f"Postmortem drafted by {user.full_name}",
        metadata_json={"postmortem_id": str(pm.id)},
    )

    return await _enrich_postmortem(pm, session)


@router.get("/{postmortem_id}", response_model=PostmortemRead)
async def get_postmortem(
    postmortem_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PostmortemRead:
    pm = await PostmortemRepository.get_by_id(session, postmortem_id)
    if pm is None:
        raise AppError("POSTMORTEM_NOT_FOUND", "Postmortem not found", 404)
    return await _enrich_postmortem(pm, session)


@router.get("/by-incident/{incident_id}", response_model=PostmortemRead | None)
async def get_postmortem_by_incident(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PostmortemRead | None:
    pm = await PostmortemRepository.get_by_incident_id(session, incident_id)
    if pm is None:
        return None
    return await _enrich_postmortem(pm, session)


@router.patch("/{postmortem_id}", response_model=PostmortemRead)
async def update_postmortem(
    postmortem_id: UUID,
    payload: PostmortemUpdate,
    session: AsyncSession = Depends(get_session),
    user: UserAuth = Depends(require_permission("postmortem:create")),
) -> PostmortemRead:
    pm = await PostmortemRepository.get_by_id(session, postmortem_id)
    if pm is None:
        raise AppError("POSTMORTEM_NOT_FOUND", "Postmortem not found", 404)

    updates = payload.model_dump(exclude_unset=True)
    updated = await PostmortemRepository.update_postmortem(session, pm, updates)

    if payload.status == "APPROVED":
        await IncidentRepository.add_timeline_event(
            session,
            incident_id=pm.incident_id,
            actor_id=user.id,
            event_type="PostmortemApproved",
            message=f"Postmortem approved by {user.full_name}",
            metadata_json={"postmortem_id": str(pm.id)},
        )

    return await _enrich_postmortem(updated, session)
