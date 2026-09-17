from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import UserAuth, current_user
from app.core.database import clean_doc, get_db
from app.core.errors import AppError
from app.schemas.notification import NotificationRead

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: UserAuth = Depends(current_user),
) -> list[NotificationRead]:
    cursor = (
        db.notifications.find({"$or": [{"user_id": str(user.id)}, {"user_id": None}]})
        .sort("created_at", -1)
        .limit(100)
    )
    docs = await cursor.to_list(100)
    return [NotificationRead(**clean_doc(d)) for d in docs]  # type: ignore


@router.post("/{notification_id}/read", response_model=NotificationRead)
async def mark_read(
    notification_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: UserAuth = Depends(current_user),
) -> NotificationRead:
    nid = str(notification_id)
    doc = await db.notifications.find_one({"id": nid})
    if doc is None or doc.get("user_id") not in {None, str(user.id)}:
        raise AppError("NOTIFICATION_NOT_FOUND", "Notification not found", 404)

    now = datetime.now(UTC)
    await db.notifications.update_one({"id": nid}, {"$set": {"read_at": now}})
    updated = await db.notifications.find_one({"id": nid})
    return NotificationRead(**clean_doc(updated))  # type: ignore
