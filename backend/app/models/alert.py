from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import AlertSeverity, AlertStatus


class Alert(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_fingerprint", "fingerprint"),
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_service_id", "service_id"),
        UniqueConstraint("fingerprint", name="uq_alerts_fingerprint"),
    )

    service_id: Mapped[UUID] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"))
    incident_id: Mapped[UUID | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(120))
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(300))
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[AlertStatus] = mapped_column(Enum(AlertStatus), default=AlertStatus.OPEN)
