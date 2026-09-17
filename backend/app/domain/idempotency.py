import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.core.errors import AppError


def payload_hash(payload: Any) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def get_idempotent_response(
    db: Any, key: str | None, scope: str, request_hash: str
) -> dict | None:
    if key is None:
        return None

    if hasattr(db, "idempotency_records"):
        record = await db.idempotency_records.find_one({"key": key, "scope": scope})
        if record is None:
            return None
        if record.get("request_hash") != request_hash:
            raise AppError(
                "IDEMPOTENCY_KEY_REUSED",
                "Idempotency key was reused with a different payload",
                409,
            )
        return record.get("response_json")

    # Fallback if an AsyncSession is passed
    try:
        from sqlalchemy import select

        from app.models.idempotency import IdempotencyRecord

        record = await db.scalar(
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
    except Exception:
        return None


async def store_idempotent_response(
    db: Any,
    key: str | None,
    scope: str,
    request_hash: str,
    response_json: dict,
) -> None:
    if key is None:
        return

    if hasattr(db, "idempotency_records"):
        await db.idempotency_records.insert_one(
            {
                "key": key,
                "scope": scope,
                "request_hash": request_hash,
                "response_json": response_json,
                "created_at": datetime.now(UTC),
            }
        )
        return

    try:
        from app.models.idempotency import IdempotencyRecord

        db.add(
            IdempotencyRecord(
                key=key,
                scope=scope,
                request_hash=request_hash,
                response_json=response_json,
            )
        )
    except Exception:
        pass
