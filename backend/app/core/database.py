from collections.abc import AsyncGenerator
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# --- MongoDB Client & Database ---
_mongo_client: AsyncIOMotorClient | None = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(
            settings.mongodb_url,
            serverSelectionTimeoutMS=5000,
            maxPoolSize=50,
            minPoolSize=5,
        )
    return _mongo_client


def get_database() -> AsyncIOMotorDatabase:
    client = get_mongo_client()
    return client.get_database(settings.mongodb_db_name)


async def get_db() -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    db = get_database()
    yield db


def clean_doc(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Helper to ensure MongoDB document is compatible with Pydantic schemas."""
    if doc is None:
        return None
    d = dict(doc)
    if "_id" in d:
        if "id" not in d or not d["id"]:
            d["id"] = str(d["_id"])
        del d["_id"]
    for key in ("status", "severity", "criticality", "role"):
        if key in d and isinstance(d[key], str):
            val = d[key].upper()
            if val == "FIRING":
                val = "OPEN"
            d[key] = val
    return d


def clean_docs(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [clean_doc(d) for d in docs if d is not None]  # type: ignore


async def init_db_indexes() -> None:
    """Ensure essential indexes exist on MongoDB collections."""
    try:
        db = get_database()
        await db.users.create_index("email", unique=True)
        await db.users.create_index("id", unique=True)
        await db.services.create_index("slug", unique=True)
        await db.services.create_index("id", unique=True)
        await db.incidents.create_index("id", unique=True)
        await db.incidents.create_index([("service_id", 1), ("status", 1)])
        await db.incidents.create_index("created_at")
        await db.alerts.create_index("id", unique=True)
        await db.alerts.create_index("fingerprint")
        await db.alerts.create_index([("incident_id", 1), ("status", 1)])
        await db.timeline_events.create_index("incident_id")
        await db.postmortems.create_index("incident_id", unique=True)
        await db.runbooks.create_index("service_id")
        await db.notifications.create_index([("user_id", 1), ("is_read", 1)])
        await db.idempotency_records.create_index("key", unique=True)
    except Exception as exc:
        print(f"Warning: could not initialize MongoDB indexes: {exc}")


# --- Legacy SQL Engine retained for backward compatibility / fallback ---
def _create_engine():
    try:
        return create_async_engine(settings.async_database_url, pool_pre_ping=True)
    except Exception:
        return create_async_engine("sqlite+aiosqlite:///:memory:")


engine = _create_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
