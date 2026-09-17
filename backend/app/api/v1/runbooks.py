from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.errors import AppError
from app.models.runbook import Runbook
from app.models.service import Service
from app.models.user import User
from app.schemas.runbook import RunbookCreate, RunbookRead, RunbookUpdate

router = APIRouter(prefix="/runbooks", tags=["runbooks"])


@router.get("", response_model=list[RunbookRead])
async def list_runbooks(
    service_id: UUID | None = Query(default=None),
    incident_type: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[RunbookRead]:
    stmt = select(Runbook, Service.name.label("service_name")).outerjoin(
        Service, Runbook.service_id == Service.id
    )
    if service_id is not None:
        stmt = stmt.where(Runbook.service_id == service_id)
    if incident_type is not None:
        stmt = stmt.where(Runbook.incident_type == incident_type)

    stmt = stmt.order_by(Runbook.title)
    rows = (await session.execute(stmt)).all()
    return [
        RunbookRead(
            id=r.id,
            service_id=r.service_id,
            service_name=s_name,
            title=r.title,
            incident_type=r.incident_type,
            body=r.body,
            owner_id=r.owner_id,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r, s_name in rows
    ]


@router.post("", response_model=RunbookRead, status_code=201)
async def create_runbook(
    payload: RunbookCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("service:update")),
) -> RunbookRead:
    runbook = Runbook(
        service_id=payload.service_id,
        title=payload.title,
        incident_type=payload.incident_type,
        body=payload.body,
        owner_id=user.id,
    )
    session.add(runbook)
    await session.commit()
    await session.refresh(runbook)
    return await get_runbook(runbook.id, session)


@router.get("/{runbook_id}", response_model=RunbookRead)
async def get_runbook(
    runbook_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> RunbookRead:
    stmt = (
        select(Runbook, Service.name.label("service_name"))
        .outerjoin(Service, Runbook.service_id == Service.id)
        .where(Runbook.id == runbook_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise AppError("RUNBOOK_NOT_FOUND", "Runbook not found", 404)
    r, s_name = row
    return RunbookRead(
        id=r.id,
        service_id=r.service_id,
        service_name=s_name,
        title=r.title,
        incident_type=r.incident_type,
        body=r.body,
        owner_id=r.owner_id,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.patch("/{runbook_id}", response_model=RunbookRead)
async def update_runbook(
    runbook_id: UUID,
    payload: RunbookUpdate,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission("service:update")),
) -> RunbookRead:
    runbook = await session.get(Runbook, runbook_id)
    if runbook is None:
        raise AppError("RUNBOOK_NOT_FOUND", "Runbook not found", 404)

    if payload.service_id is not None:
        runbook.service_id = payload.service_id
    if payload.title is not None:
        runbook.title = payload.title
    if payload.incident_type is not None:
        runbook.incident_type = payload.incident_type
    if payload.body is not None:
        runbook.body = payload.body

    await session.commit()
    return await get_runbook(runbook_id, session)


@router.delete("/{runbook_id}", status_code=204)
async def delete_runbook(
    runbook_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission("service:update")),
) -> None:
    runbook = await session.get(Runbook, runbook_id)
    if runbook is None:
        raise AppError("RUNBOOK_NOT_FOUND", "Runbook not found", 404)
    await session.delete(runbook)
    await session.commit()
