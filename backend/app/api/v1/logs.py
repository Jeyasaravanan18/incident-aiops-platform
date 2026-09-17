from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import clean_doc, get_db
from app.domain.redaction import redact_mapping, redact_text
from app.schemas.log import LogIngest, LogRead

router = APIRouter(prefix="/logs", tags=["logs"])


@router.post("", response_model=LogRead, status_code=201)
async def ingest_log(payload: LogIngest, db: AsyncIOMotorDatabase = Depends(get_db)) -> LogRead:
    # Resolve service_id if service exists by name or slug
    service = await db.services.find_one(
        {
            "$or": [
                {"slug": payload.service},
                {"name": {"$regex": f"^{payload.service}$", "$options": "i"}},
            ]
        }
    )
    service_id = str(service["id"]) if service else None

    entry_id = str(uuid4())
    ts = payload.timestamp or datetime.now(UTC)

    entry = {
        "id": entry_id,
        "timestamp": ts,
        "service_id": service_id,
        "service_name": payload.service,
        "level": payload.level.upper(),
        "message": redact_text(payload.message),
        "trace_id": payload.trace_id,
        "request_id": payload.request_id,
        "metadata_json": redact_mapping(payload.metadata),
    }
    await db.logs.insert_one(entry)
    return LogRead(**clean_doc(entry))  # type: ignore


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
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> list[LogRead]:
    query: dict[str, Any] = {}

    if service:
        query["service_name"] = {"$regex": service, "$options": "i"}
    if level:
        query["level"] = level.upper()
    if trace_id:
        query["trace_id"] = trace_id
    if request_id:
        query["request_id"] = request_id
    if search:
        query["message"] = {"$regex": search, "$options": "i"}

    if start_time or end_time:
        ts_query: dict[str, Any] = {}
        if start_time:
            ts_query["$gte"] = start_time
        if end_time:
            ts_query["$lte"] = end_time
        query["timestamp"] = ts_query

    cursor = db.logs.find(query).sort("timestamp", -1).skip(offset).limit(limit)
    docs = await cursor.to_list(limit)
    return [LogRead(**clean_doc(d)) for d in docs]  # type: ignore
