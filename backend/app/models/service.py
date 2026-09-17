from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import Criticality, ServiceStatus


class Service(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "services"

    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    repository: Mapped[str | None] = mapped_column(String(500))
    environment: Mapped[str] = mapped_column(String(80), default="production")
    health_endpoint: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[ServiceStatus] = mapped_column(
        Enum(ServiceStatus), default=ServiceStatus.UNKNOWN
    )
    criticality: Mapped[Criticality] = mapped_column(Enum(Criticality), default=Criticality.MEDIUM)


class ServiceHealthCheck(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "service_health_checks"
    __table_args__ = (Index("ix_service_health_service_created", "service_id", "created_at"),)

    service_id: Mapped[UUID] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"))
    http_status: Mapped[int | None] = mapped_column(Integer)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    availability: Mapped[bool] = mapped_column(default=False)
    error: Mapped[str | None] = mapped_column(Text)
