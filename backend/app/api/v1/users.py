from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import UserAuth, current_user
from app.core.database import clean_doc, get_db
from app.domain.permissions import ROLE_PERMISSIONS
from app.models.enums import Role
from app.schemas.user import UserMe, UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMe)
async def get_me(
    user: UserAuth = Depends(current_user), db: AsyncIOMotorDatabase = Depends(get_db)
) -> UserMe:
    doc = await db.users.find_one({"id": user.id})
    created_at = doc.get("created_at") if doc else datetime.now(UTC)
    permissions = list(ROLE_PERMISSIONS.get(Role(user.role), set()))
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
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: UserAuth = Depends(current_user),
) -> list[UserRead]:
    cursor = db.users.find({"is_active": True}).sort("full_name", 1)
    docs = await cursor.to_list(100)
    return [UserRead(**clean_doc(d)) for d in docs]  # type: ignore
