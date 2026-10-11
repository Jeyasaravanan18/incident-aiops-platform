"""Idempotency engine with SHA-256 payload hashing and persistent database caching."""

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.idempotency import IdempotencyRecord


def payload_hash(payload: Any) -> str:
    """Computes a deterministic SHA-256 hex digest of a JSON-serializable payload."""
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def get_idempotent_response(
    session: AsyncSession, key: str | None, scope: str, request_hash: str
) -> dict | None:
    """Checks whether an idempotent request was previously executed with the exact payload."""
    if key is None:
        return None

    stmt = select(IdempotencyRecord).where(
        IdempotencyRecord.key == key,
        IdempotencyRecord.scope == scope,
    )
    record = await session.scalar(stmt)
    if record is None:
        return None
    if record.request_hash != request_hash:
        raise AppError(
            "IDEMPOTENCY_KEY_REUSED",
            "Idempotency key was reused with a different payload",
            409,
        )
    return record.response_json


async def store_idempotent_response(
    session: AsyncSession,
    key: str | None,
    scope: str,
    request_hash: str,
    response_json: dict,
) -> None:
    """Caches the executed response for an idempotency key and scope."""
    if key is None:
        return

    record = IdempotencyRecord(
        key=key,
        scope=scope,
        request_hash=request_hash,
        response_json=response_json,
    )
    session.add(record)
    await session.flush()
