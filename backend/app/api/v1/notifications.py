from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.core.database import get_session
from app.core.errors import AppError
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationRead

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> list[Notification]:
    return list(
        await session.scalars(
            select(Notification)
            .where((Notification.user_id == user.id) | (Notification.user_id.is_(None)))
            .order_by(Notification.created_at.desc())
            .limit(100)
        )
    )


@router.post("/{notification_id}/read", response_model=NotificationRead)
async def mark_read(
    notification_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> Notification:
    notification = await session.get(Notification, notification_id)
    if notification is None or notification.user_id not in {None, user.id}:
        raise AppError("NOTIFICATION_NOT_FOUND", "Notification not found", 404)
    notification.read_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(notification)
    return notification
