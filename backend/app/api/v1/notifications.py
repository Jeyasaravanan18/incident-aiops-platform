from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UserAuth, current_user
from app.core.database import get_session
from app.core.errors import AppError
from app.repositories.notification_repo import NotificationRepository
from app.schemas.notification import NotificationRead

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    session: AsyncSession = Depends(get_session),
    user: UserAuth = Depends(current_user),
) -> list[NotificationRead]:
    notes = await NotificationRepository.list_notifications(session, user_id=user.id, limit=100)
    return [
        NotificationRead(
            id=n.id,
            user_id=n.user_id,
            incident_id=n.incident_id,
            title=n.title,
            body=n.body,
            channel=n.channel,
            status=n.status,
            read_at=n.read_at,
            created_at=n.created_at,
        )
        for n in notes
    ]


@router.post("/{notification_id}/read", response_model=NotificationRead)
async def mark_read(
    notification_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: UserAuth = Depends(current_user),
) -> NotificationRead:
    note = await NotificationRepository.get_by_id(session, notification_id)
    if note is None or (note.user_id is not None and note.user_id != user.id):
        raise AppError("NOTIFICATION_NOT_FOUND", "Notification not found", 404)

    updated = await NotificationRepository.mark_read(session, note)
    return NotificationRead(
        id=updated.id,
        user_id=updated.user_id,
        incident_id=updated.incident_id,
        title=updated.title,
        body=updated.body,
        channel=updated.channel,
        status=updated.status,
        read_at=updated.read_at,
        created_at=updated.created_at,
    )
