from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.core.database import get_session
from app.domain.permissions import ROLE_PERMISSIONS
from app.models.enums import Role
from app.models.user import User
from app.schemas.user import UserMe, UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMe)
async def get_me(user: User = Depends(current_user)) -> UserMe:
    permissions = list(ROLE_PERMISSIONS.get(Role(user.role), set()))
    return UserMe(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        permissions=permissions,
    )


@router.get("", response_model=list[UserRead])
async def list_users(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
) -> list[User]:
    stmt = select(User).where(User.is_active.is_(True)).order_by(User.full_name)
    return list(await session.scalars(stmt))
