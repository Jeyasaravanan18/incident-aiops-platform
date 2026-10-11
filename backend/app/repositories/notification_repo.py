"""In-App Notification Repository."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


class NotificationRepository:
    @staticmethod
    async def list_notifications(
        session: AsyncSession,
        user_id: UUID | None = None,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        stmt = select(Notification)
        if user_id is not None:
            stmt = stmt.where((Notification.user_id == user_id) | (Notification.user_id.is_(None)))
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)
        result = await session.scalars(stmt)
        return list(result.all())

    @staticmethod
    async def get_by_id(session: AsyncSession, notification_id: UUID) -> Notification | None:
        return await session.get(Notification, notification_id)

    @staticmethod
    async def mark_read(session: AsyncSession, notification: Notification) -> Notification:
        notification.read_at = datetime.now(UTC)
        await session.flush()
        return notification
