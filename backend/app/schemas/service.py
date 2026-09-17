from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from app.models.enums import Criticality, ServiceStatus


class ServiceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]+$")
    description: str | None = None
    repository: str | None = None
    environment: str = "production"
    health_endpoint: HttpUrl | None = None
    criticality: Criticality = Criticality.MEDIUM


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = None
    repository: str | None = None
    environment: str | None = None
    health_endpoint: HttpUrl | None = None
    criticality: Criticality | None = None
    status: ServiceStatus | None = None


class ServiceHealthCheckRead(BaseModel):
    id: UUID
    service_id: UUID
    http_status: int | None
    response_time_ms: int | None
    availability: bool
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ServiceRead(BaseModel):
    id: UUID
    name: str
    slug: str
    description: str | None
    repository: str | None
    environment: str
    health_endpoint: str | None
    status: ServiceStatus
    criticality: Criticality
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ServiceDetailRead(ServiceRead):
    uptime_percentage: float = 100.0
    avg_response_time_ms: float | None = None
    active_incidents_count: int = 0
    recent_health_checks: list[ServiceHealthCheckRead] = Field(default_factory=list)
