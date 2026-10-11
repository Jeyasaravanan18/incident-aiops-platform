"""Pytest configuration, fixtures, and authentication helpers for integration tests.

Provides:
  - Database session fixture with transactional rollback / cleanup.
  - httpx.AsyncClient fixture bound to FastAPI app with ASGITransport.
  - Auth helper fixtures providing JWT bearer tokens for ADMIN, RESPONDER, and VIEWER roles.
"""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.enums import Criticality, Role, ServiceStatus
from app.models.service import Service
from app.models.user import User


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yields a dedicated async database session for integration tests."""
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Yields an httpx AsyncClient connected to the FastAPI application via ASGITransport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Creates and returns an active ADMIN user."""
    user = User(
        id=uuid4(),
        email=f"admin-{uuid4().hex[:8]}@example.com",
        full_name="Admin User",
        password_hash=hash_password("SuperSecretAdmin123!"),
        role=Role.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def responder_user(db_session: AsyncSession) -> User:
    """Creates and returns an active RESPONDER (ENGINEER) user."""
    user = User(
        id=uuid4(),
        email=f"responder-{uuid4().hex[:8]}@example.com",
        full_name="Responder User",
        password_hash=hash_password("SuperSecretResp123!"),
        role=Role.ENGINEER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def viewer_user(db_session: AsyncSession) -> User:
    """Creates and returns an active VIEWER user."""
    user = User(
        id=uuid4(),
        email=f"viewer-{uuid4().hex[:8]}@example.com",
        full_name="Viewer User",
        password_hash=hash_password("SuperSecretView123!"),
        role=Role.VIEWER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
def admin_headers(admin_user: User) -> dict[str, str]:
    """Returns Authorization bearer headers for ADMIN user."""
    token = create_access_token(admin_user.id, str(admin_user.role.value))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def responder_headers(responder_user: User) -> dict[str, str]:
    """Returns Authorization bearer headers for RESPONDER user."""
    token = create_access_token(responder_user.id, str(responder_user.role.value))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def viewer_headers(viewer_user: User) -> dict[str, str]:
    """Returns Authorization bearer headers for VIEWER user."""
    token = create_access_token(viewer_user.id, str(viewer_user.role.value))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_service(db_session: AsyncSession) -> Service:
    """Creates and returns a healthy test service."""
    svc = Service(
        id=uuid4(),
        name=f"Fixture Service {uuid4().hex[:6]}",
        slug=f"svc-{uuid4().hex[:8]}",
        status=ServiceStatus.HEALTHY,
        criticality=Criticality.HIGH,
    )
    db_session.add(svc)
    await db_session.commit()
    return svc
