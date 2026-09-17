from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PostmortemCreate(BaseModel):
    incident_id: UUID
    summary: str
    impact: str
    timeline: str
    root_cause: str | None = None
    contributing_factors: str | None = None
    resolution: str | None = None
    preventive_actions: str | None = None
    lessons_learned: str | None = None


class PostmortemUpdate(BaseModel):
    summary: str | None = None
    impact: str | None = None
    timeline: str | None = None
    root_cause: str | None = None
    contributing_factors: str | None = None
    resolution: str | None = None
    preventive_actions: str | None = None
    lessons_learned: str | None = None
    status: str | None = None


class PostmortemRead(PostmortemCreate):
    id: UUID
    incident_title: str | None = None
    owner_id: UUID | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
