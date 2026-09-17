from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.errors import AppError
from app.models.incident import Incident, TimelineEvent
from app.models.postmortem import Postmortem
from app.models.user import User
from app.schemas.postmortem import PostmortemCreate, PostmortemRead, PostmortemUpdate

router = APIRouter(prefix="/postmortems", tags=["postmortems"])


@router.get("", response_model=list[PostmortemRead])
async def list_postmortems(session: AsyncSession = Depends(get_session)) -> list[PostmortemRead]:
    stmt = (
        select(Postmortem, Incident.title.label("incident_title"))
        .outerjoin(Incident, Postmortem.incident_id == Incident.id)
        .order_by(Postmortem.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        PostmortemRead(
            id=p.id,
            incident_id=p.incident_id,
            incident_title=inc_title,
            summary=p.summary,
            impact=p.impact,
            timeline=p.timeline,
            root_cause=p.root_cause,
            contributing_factors=p.contributing_factors,
            resolution=p.resolution,
            preventive_actions=p.preventive_actions,
            lessons_learned=p.lessons_learned,
            owner_id=p.owner_id,
            status=p.status,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p, inc_title in rows
    ]


@router.post("", response_model=PostmortemRead, status_code=201)
async def create_postmortem(
    payload: PostmortemCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("postmortem:create")),
) -> PostmortemRead:
    incident = await session.get(Incident, payload.incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    existing = await session.scalar(
        select(Postmortem).where(Postmortem.incident_id == payload.incident_id)
    )
    if existing:
        raise AppError(
            "POSTMORTEM_ALREADY_EXISTS", "Postmortem already exists for this incident", 409
        )

    postmortem = Postmortem(**payload.model_dump(), owner_id=user.id, status="DRAFT")
    session.add(postmortem)

    session.add(
        TimelineEvent(
            incident_id=incident.id,
            actor_id=user.id,
            event_type="PostmortemCreated",
            message=f"Postmortem drafted by {user.full_name}",
            metadata_json={"postmortem_id": str(postmortem.id)},
        )
    )
    await session.commit()
    await session.refresh(postmortem)
    return await get_postmortem(postmortem.id, session)


@router.get("/{postmortem_id}", response_model=PostmortemRead)
async def get_postmortem(
    postmortem_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PostmortemRead:
    stmt = (
        select(Postmortem, Incident.title.label("incident_title"))
        .outerjoin(Incident, Postmortem.incident_id == Incident.id)
        .where(Postmortem.id == postmortem_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise AppError("POSTMORTEM_NOT_FOUND", "Postmortem not found", 404)
    p, inc_title = row
    return PostmortemRead(
        id=p.id,
        incident_id=p.incident_id,
        incident_title=inc_title,
        summary=p.summary,
        impact=p.impact,
        timeline=p.timeline,
        root_cause=p.root_cause,
        contributing_factors=p.contributing_factors,
        resolution=p.resolution,
        preventive_actions=p.preventive_actions,
        lessons_learned=p.lessons_learned,
        owner_id=p.owner_id,
        status=p.status,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("/by-incident/{incident_id}", response_model=PostmortemRead | None)
async def get_postmortem_by_incident(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PostmortemRead | None:
    stmt = (
        select(Postmortem, Incident.title.label("incident_title"))
        .outerjoin(Incident, Postmortem.incident_id == Incident.id)
        .where(Postmortem.incident_id == incident_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    p, inc_title = row
    return PostmortemRead(
        id=p.id,
        incident_id=p.incident_id,
        incident_title=inc_title,
        summary=p.summary,
        impact=p.impact,
        timeline=p.timeline,
        root_cause=p.root_cause,
        contributing_factors=p.contributing_factors,
        resolution=p.resolution,
        preventive_actions=p.preventive_actions,
        lessons_learned=p.lessons_learned,
        owner_id=p.owner_id,
        status=p.status,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.patch("/{postmortem_id}", response_model=PostmortemRead)
async def update_postmortem(
    postmortem_id: UUID,
    payload: PostmortemUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("postmortem:create")),
) -> PostmortemRead:
    postmortem = await session.get(Postmortem, postmortem_id)
    if postmortem is None:
        raise AppError("POSTMORTEM_NOT_FOUND", "Postmortem not found", 404)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(postmortem, field, value)

    if payload.status == "APPROVED":
        session.add(
            TimelineEvent(
                incident_id=postmortem.incident_id,
                actor_id=user.id,
                event_type="PostmortemApproved",
                message=f"Postmortem approved by {user.full_name}",
                metadata_json={"postmortem_id": str(postmortem.id)},
            )
        )

    await session.commit()
    return await get_postmortem(postmortem_id, session)
