from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UserAuth, require_permission
from app.core.database import get_session
from app.core.errors import AppError
from app.models.runbook import Runbook
from app.repositories.runbook_repo import RunbookRepository
from app.repositories.service_repo import ServiceRepository
from app.schemas.runbook import RunbookCreate, RunbookRead, RunbookUpdate

router = APIRouter(prefix="/runbooks", tags=["runbooks"])


async def _enrich_runbook(rb: Runbook, session: AsyncSession) -> RunbookRead:
    s_name = None
    if rb.service_id:
        service = await ServiceRepository.get_by_id(session, rb.service_id)
        if service:
            s_name = service.name

    return RunbookRead(
        id=rb.id,
        service_id=rb.service_id,
        service_name=s_name,
        title=rb.title,
        incident_type=rb.incident_type,
        body=rb.body or "",
        owner_id=rb.owner_id,
        created_at=rb.created_at,
        updated_at=rb.updated_at,
    )


@router.get("", response_model=list[RunbookRead])
async def list_runbooks(
    service_id: UUID | None = Query(default=None),
    incident_type: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[RunbookRead]:
    runbooks = await RunbookRepository.list_runbooks(
        session, service_id=service_id, incident_type=incident_type
    )

    service_ids = {rb.service_id for rb in runbooks if rb.service_id}
    s_map: dict[UUID, str] = {}
    for sid in service_ids:
        svc = await ServiceRepository.get_by_id(session, sid)
        if svc:
            s_map[sid] = svc.name

    return [
        RunbookRead(
            id=rb.id,
            service_id=rb.service_id,
            service_name=s_map.get(rb.service_id),
            title=rb.title,
            incident_type=rb.incident_type,
            body=rb.body or "",
            owner_id=rb.owner_id,
            created_at=rb.created_at,
            updated_at=rb.updated_at,
        )
        for rb in runbooks
    ]


@router.post("", response_model=RunbookRead, status_code=201)
async def create_runbook(
    payload: RunbookCreate,
    session: AsyncSession = Depends(get_session),
    user: UserAuth = Depends(require_permission("service:update")),
) -> RunbookRead:
    rb = await RunbookRepository.create_runbook(
        session,
        service_id=payload.service_id,
        title=payload.title,
        incident_type=payload.incident_type,
        body=payload.body,
        owner_id=user.id,
    )
    return await _enrich_runbook(rb, session)


@router.get("/{runbook_id}", response_model=RunbookRead)
async def get_runbook(
    runbook_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> RunbookRead:
    rb = await RunbookRepository.get_by_id(session, runbook_id)
    if rb is None:
        raise AppError("RUNBOOK_NOT_FOUND", "Runbook not found", 404)
    return await _enrich_runbook(rb, session)


@router.patch("/{runbook_id}", response_model=RunbookRead)
async def update_runbook(
    runbook_id: UUID,
    payload: RunbookUpdate,
    session: AsyncSession = Depends(get_session),
    _: UserAuth = Depends(require_permission("service:update")),
) -> RunbookRead:
    rb = await RunbookRepository.get_by_id(session, runbook_id)
    if rb is None:
        raise AppError("RUNBOOK_NOT_FOUND", "Runbook not found", 404)

    updates = {}
    if payload.service_id is not None:
        updates["service_id"] = payload.service_id
    if payload.title is not None:
        updates["title"] = payload.title
    if payload.incident_type is not None:
        updates["incident_type"] = payload.incident_type
    if payload.body is not None:
        updates["body"] = payload.body

    updated = await RunbookRepository.update_runbook(session, rb, updates)
    return await _enrich_runbook(updated, session)


@router.delete("/{runbook_id}", status_code=204)
async def delete_runbook(
    runbook_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: UserAuth = Depends(require_permission("service:update")),
) -> None:
    rb = await RunbookRepository.get_by_id(session, runbook_id)
    if rb is None:
        raise AppError("RUNBOOK_NOT_FOUND", "Runbook not found", 404)
    await RunbookRepository.delete_runbook(session, rb)
