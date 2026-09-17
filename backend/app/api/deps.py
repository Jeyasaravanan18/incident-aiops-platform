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

bearer = HTTPBearer(auto_error=False)


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise AppError("AUTH_REQUIRED", "Authentication required", 401)
    payload = decode_token(credentials.credentials)
    user_id = UUID(payload["sub"])
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError("AUTH_REQUIRED", "Authentication required", 401)
    return user


def require_permission(permission: str):
    async def dependency(user: User = Depends(current_user)) -> User:
        if not has_permission(Role(user.role), permission):
            raise AppError("FORBIDDEN", "Insufficient permissions", 403)
        return user

    return dependency


async def idempotency_key(idempotency_key: str | None = Header(default=None)) -> str | None:
    return idempotency_key
