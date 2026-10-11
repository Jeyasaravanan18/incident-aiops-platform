from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.domain.redaction import redact_mapping, redact_text
from app.repositories.log_repo import LogRepository
from app.repositories.service_repo import ServiceRepository
from app.schemas.log import LogIngest, LogRead

router = APIRouter(prefix="/logs", tags=["logs"])


@router.post("", response_model=LogRead, status_code=201)
async def ingest_log(payload: LogIngest, session: AsyncSession = Depends(get_session)) -> LogRead:
    # Resolve service_id if service exists by slug or name
    service = await ServiceRepository.get_by_slug(session, payload.service)
    if not service:
        service = await ServiceRepository.get_by_name(session, payload.service)
    service_id = service.id if service else None

    ts = payload.timestamp or datetime.now(UTC)

    entry = await LogRepository.create_log(
        session=session,
        timestamp=ts,
        service_id=service_id,
        service_name=payload.service,
        level=payload.level,
        message=redact_text(payload.message),
        trace_id=payload.trace_id,
        request_id=payload.request_id,
        metadata_json=redact_mapping(payload.metadata),
    )

    return LogRead(
        id=entry.id,
        timestamp=entry.timestamp,
        service_id=entry.service_id,
        service_name=entry.service_name,
        level=entry.level,
        message=entry.message,
        trace_id=entry.trace_id,
        request_id=entry.request_id,
        metadata_json=entry.metadata_json or {},
        created_at=entry.created_at,
    )


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
    entries = await LogRepository.list_logs(
        session=session,
        service=service,
        level=level,
        trace_id=trace_id,
        request_id=request_id,
        search=search,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    return [
        LogRead(
            id=e.id,
            timestamp=e.timestamp,
            service_id=e.service_id,
            service_name=e.service_name,
            level=e.level,
            message=e.message,
            trace_id=e.trace_id,
            request_id=e.request_id,
            metadata_json=e.metadata_json or {},
            created_at=e.created_at,
        )
        for e in entries
    ]
