from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RunbookCreate(BaseModel):
    service_id: UUID | None = None
    title: str = Field(min_length=3, max_length=200)
    incident_type: str = Field(min_length=2, max_length=100)
    body: str = Field(min_length=10)


class RunbookUpdate(BaseModel):
    service_id: UUID | None = None
    title: str | None = Field(default=None, min_length=3, max_length=200)
    incident_type: str | None = Field(default=None, min_length=2, max_length=100)
    body: str | None = Field(default=None, min_length=10)


class RunbookRead(BaseModel):
    id: UUID
    service_id: UUID | None
    service_name: str | None = None
    title: str
    incident_type: str
    body: str
    owner_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
