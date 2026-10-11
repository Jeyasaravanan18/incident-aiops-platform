"""PostgreSQL Database Engine and Async Session Management using SQLAlchemy 2.0."""

import os
import sys
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings

is_testing = (
    os.getenv("TESTING", "").lower() in ("1", "true", "yes")
    or "pytest" in sys.modules
    or any("pytest" in arg for arg in sys.argv)
)

engine_kwargs: dict = {"pool_pre_ping": True}
if is_testing:
    engine_kwargs["poolclass"] = NullPool
else:
    engine_kwargs["pool_size"] = 20
    engine_kwargs["max_overflow"] = 10

# Primary asynchronous database engine configured with pre-ping health validation
engine = create_async_engine(settings.async_database_url, **engine_kwargs)

# Async session factory for dependency injection across API endpoints and workers
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Backward-compatibility alias for Celery worker tasks
SessionLocal = AsyncSessionLocal


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a transactional AsyncSession with automatic commit/rollback."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
