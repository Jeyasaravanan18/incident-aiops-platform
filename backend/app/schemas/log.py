from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class LogIngest(BaseModel):
    timestamp: datetime
    service: str
    level: str = Field(pattern=r"^(INFO|WARN|WARNING|ERROR|CRITICAL)$")
    message: str
    trace_id: str | None = None
    request_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class LogRead(BaseModel):
    id: UUID
    timestamp: datetime
    service_id: UUID | None
    service_name: str
    level: str
    message: str
    trace_id: str | None
    request_id: str | None
    metadata_json: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class LogListResponse(BaseModel):
    total: int
    items: list[LogRead]
