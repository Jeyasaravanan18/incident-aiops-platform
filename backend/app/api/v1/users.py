from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UserAuth, current_user
from app.core.database import get_session
from app.domain.permissions import ROLE_PERMISSIONS
from app.models.enums import Role
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserMe, UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMe)
async def get_me(
    user: UserAuth = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> UserMe:
    db_user = await UserRepository.get_by_id(session, user.id)
    created_at = db_user.created_at if db_user else datetime.now(UTC)
    role_enum = Role(user.role) if isinstance(user.role, str) else user.role
    permissions = list(ROLE_PERMISSIONS.get(role_enum, set()))
    return UserMe(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=created_at,
        permissions=permissions,
    )


@router.get("", response_model=list[UserRead])
async def list_users(
    session: AsyncSession = Depends(get_session),
    _: UserAuth = Depends(current_user),
) -> list[UserRead]:
    users = await UserRepository.list_active(session)
    return [
        UserRead(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role.value if hasattr(u.role, "value") else str(u.role),
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in users
    ]
