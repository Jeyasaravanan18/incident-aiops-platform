from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


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
