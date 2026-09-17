from typing import Any

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import decode_token
from app.domain.permissions import has_permission
from app.models.enums import Role

bearer = HTTPBearer(auto_error=False)


class UserAuth:
    """Lightweight user identity model for authentication & authorization."""

    def __init__(self, data: dict[str, Any]):
        self.id = str(data.get("id") or data.get("_id", ""))
        self.email = str(data.get("email", ""))
        self.role = str(data.get("role", "responder"))
        self.is_active = bool(data.get("is_active", True))
        self.full_name = str(data.get("full_name", ""))

    def __repr__(self) -> str:
        return f"<UserAuth id={self.id} email={self.email} role={self.role}>"


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> UserAuth:
    if credentials is None:
        raise AppError("AUTH_REQUIRED", "Authentication required", 401)
    payload = decode_token(credentials.credentials)
    user_id_str = str(payload.get("sub", ""))
    user_doc = await db.users.find_one({"id": user_id_str})
    if not user_doc and payload.get("email"):
        user_doc = await db.users.find_one({"email": payload.get("email")})
    if user_doc is None or not user_doc.get("is_active", True):
        raise AppError("AUTH_REQUIRED", "Authentication required", 401)
    return UserAuth(user_doc)


def require_permission(permission: str):
    async def dependency(user: UserAuth = Depends(current_user)) -> UserAuth:
        if not has_permission(Role(user.role), permission):
            raise AppError("FORBIDDEN", "Insufficient permissions", 403)
        return user

    return dependency


async def idempotency_key(idempotency_key: str | None = Header(default=None)) -> str | None:
    return idempotency_key
