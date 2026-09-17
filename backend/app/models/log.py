from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class LogLevel(str):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogEntry(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "log_entries"
    __table_args__ = (
        Index("ix_logs_service_timestamp", "service_id", "timestamp"),
        Index("ix_logs_level_timestamp", "level", "timestamp"),
    )

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    service_id: Mapped[UUID | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    service_name: Mapped[str] = mapped_column(String(180))
    level: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(120))
    request_id: Mapped[str | None] = mapped_column(String(120))
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
