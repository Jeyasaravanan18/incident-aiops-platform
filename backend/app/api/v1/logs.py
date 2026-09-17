from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.domain.redaction import redact_mapping, redact_text
from app.models.log import LogEntry
from app.models.service import Service
from app.schemas.log import LogIngest, LogRead

router = APIRouter(prefix="/logs", tags=["logs"])


@router.post("", response_model=LogRead, status_code=201)
async def ingest_log(payload: LogIngest, session: AsyncSession = Depends(get_session)) -> LogRead:
    # Resolve service_id if service exists by name or slug
    service = await session.scalar(
        select(Service).where(
            or_(Service.slug == payload.service, Service.name.ilike(payload.service))
        )
    )
    service_id = service.id if service else None

    entry = LogEntry(
        timestamp=payload.timestamp,
        service_id=service_id,
        service_name=payload.service,
        level=payload.level.upper(),
        message=redact_text(payload.message),
        trace_id=payload.trace_id,
        request_id=payload.request_id,
        metadata_json=redact_mapping(payload.metadata),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return LogRead.model_validate(entry)


@router.get("", response_model=list[LogRead])
async def list_logs(
    service: str | None = Query(default=None),
    level: str | None = Query(default=None),
    trace_id: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[LogRead]:
    stmt = select(LogEntry)

    if service:
        stmt = stmt.where(
            or_(
                LogEntry.service_name.ilike(f"%{service}%"),
            )
        )
    if level:
        stmt = stmt.where(LogEntry.level == level.upper())
    if trace_id:
        stmt = stmt.where(LogEntry.trace_id == trace_id)
    if request_id:
        stmt = stmt.where(LogEntry.request_id == request_id)
    if search:
        stmt = stmt.where(LogEntry.message.ilike(f"%{search}%"))
    if start_time:
        stmt = stmt.where(LogEntry.timestamp >= start_time)
    if end_time:
        stmt = stmt.where(LogEntry.timestamp <= end_time)

    stmt = stmt.order_by(LogEntry.timestamp.desc()).offset(offset).limit(limit)
    rows = await session.scalars(stmt)
    return [LogRead.model_validate(r) for r in rows]
