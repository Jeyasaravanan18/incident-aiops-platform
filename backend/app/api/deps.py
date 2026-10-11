from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.errors import AppError
from app.core.security import decode_token
from app.domain.permissions import has_permission
from app.models.enums import Role
from app.models.user import User
from app.repositories.user_repo import UserRepository

bearer = HTTPBearer(auto_error=False)


class UserAuth:
    """Lightweight user identity model for authentication & authorization."""

    def __init__(self, user: User):
        self.id = user.id
        self.email = user.email
        self.role = user.role.value if hasattr(user.role, "value") else str(user.role)
        self.is_active = user.is_active
        self.full_name = user.full_name

    def __repr__(self) -> str:
        return f"<UserAuth id={self.id} email={self.email} role={self.role}>"


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> UserAuth:
    """Extracts and validates JWT credentials, returning the authenticated user identity."""
    if credentials is None:
        raise AppError("AUTH_REQUIRED", "Authentication required", 401)
    try:
        payload = decode_token(credentials.credentials)
    except Exception as exc:
        raise AppError("AUTH_REQUIRED", f"Authentication failed: {exc}", 401) from exc

    user_id_str = str(payload.get("sub", ""))
    user: User | None = None
    try:
        user_uuid = UUID(user_id_str)
        user = await UserRepository.get_by_id(session, user_uuid)
    except ValueError:
        pass

    if user is None and payload.get("email"):
        user = await UserRepository.get_by_email(session, str(payload.get("email")))

    if user is None or not user.is_active:
        raise AppError("AUTH_REQUIRED", "Authentication required", 401)

    return UserAuth(user)


def require_permission(permission: str):
    """Enforces role-based permission requirements for protected endpoints."""

    async def dependency(user: UserAuth = Depends(current_user)) -> UserAuth:
        if not has_permission(Role(user.role), permission):
            raise AppError("FORBIDDEN", "Insufficient permissions", 403)
        return user

    return dependency


async def idempotency_key(idempotency_key: str | None = Header(default=None)) -> str | None:
    return idempotency_key
