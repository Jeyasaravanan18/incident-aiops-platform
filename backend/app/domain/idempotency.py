import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.idempotency import IdempotencyRecord


def payload_hash(payload: Any) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def get_idempotent_response(
    session: AsyncSession, key: str | None, scope: str, request_hash: str
) -> dict | None:
    if key is None:
        return None
    record = await session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.key == key,
            IdempotencyRecord.scope == scope,
        )
    )
    if record is None:
        return None
    if record.request_hash != request_hash:
        raise AppError(
            "IDEMPOTENCY_KEY_REUSED",
            "Idempotency key was reused with a different payload",
            409,
        )
    return record.response_json


def store_idempotent_response(
    session: AsyncSession,
    key: str | None,
    scope: str,
    request_hash: str,
    response_json: dict,
) -> None:
    if key is None:
        return
    session.add(
        IdempotencyRecord(
            key=key,
            scope=scope,
            request_hash=request_hash,
            response_json=response_json,
        )
    )
