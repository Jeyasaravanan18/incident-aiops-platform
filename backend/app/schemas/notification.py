from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationRead(BaseModel):
    id: UUID
    title: str
    body: str
    resource_type: str | None
    resource_id: UUID | None
    read_at: datetime | None

    model_config = {"from_attributes": True}
