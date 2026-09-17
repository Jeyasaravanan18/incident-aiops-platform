from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import AlertSeverity, AlertStatus


class AlertCreate(BaseModel):
    service_id: UUID
    source: str = Field(max_length=120)
    severity: AlertSeverity
    title: str = Field(max_length=300)
    description: str | None = None
    fingerprint: str = Field(max_length=300)
    metadata: dict = Field(default_factory=dict)


class AlertAcknowledgeRequest(BaseModel):
    reason: str | None = None


class AlertSuppressRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    duration_minutes: int = Field(default=60, ge=1, le=1440)


class AlertResolveRequest(BaseModel):
    reason: str | None = None


class AlertRead(BaseModel):
    id: UUID
    service_id: UUID
    service_name: str | None = None
    incident_id: UUID | None
    source: str
    severity: AlertSeverity
    title: str
    description: str | None = None
    fingerprint: str
    metadata_json: dict = Field(default_factory=dict)
    first_seen: datetime
    last_seen: datetime
    occurrence_count: int
    status: AlertStatus
    created_at: datetime

    model_config = {"from_attributes": True}
