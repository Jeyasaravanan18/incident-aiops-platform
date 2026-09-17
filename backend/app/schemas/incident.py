from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import IncidentSeverity, IncidentStatus


class IncidentCreate(BaseModel):
    service_id: UUID
    title: str = Field(min_length=3, max_length=300)
    description: str | None = None
    severity: IncidentSeverity = IncidentSeverity.SEV4


class IncidentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = None
    severity: IncidentSeverity | None = None


class IncidentTransition(BaseModel):
    status: IncidentStatus
    reason: str | None = None


class IncidentReopen(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


class IncidentAssignRequest(BaseModel):
    assignee_id: UUID
    reason: str | None = None


class IncidentAssignmentRead(BaseModel):
    id: UUID
    incident_id: UUID
    assignee_id: UUID
    assigned_by_id: UUID | None
    reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class IncidentCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class IncidentCommentRead(BaseModel):
    id: UUID
    incident_id: UUID
    author_id: UUID
    author_name: str | None = None
    body: str
    created_at: datetime
    edited_at: datetime | None

    model_config = {"from_attributes": True}


class TimelineEventRead(BaseModel):
    id: UUID
    incident_id: UUID
    actor_id: UUID | None = None
    actor_name: str | None = None
    event_type: str
    message: str
    metadata_json: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class IncidentRead(BaseModel):
    id: UUID
    service_id: UUID
    service_name: str | None = None
    title: str
    description: str | None = None
    status: IncidentStatus
    severity: IncidentSeverity
    detected_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None = None
    assignee_id: UUID | None
    assignee_name: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IncidentDetailRead(IncidentRead):
    timeline_events: list[TimelineEventRead] = Field(default_factory=list)
    comments: list[IncidentCommentRead] = Field(default_factory=list)
    alert_count: int = 0
