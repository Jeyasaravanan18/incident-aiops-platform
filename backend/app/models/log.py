from datetime import datetime

from sqlalchemy import Computed, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
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
        Index("ix_log_entries_metadata_json_gin", "metadata_json", postgresql_using="gin"),
        Index("ix_log_entries_search_vector_gin", "search_vector", postgresql_using="gin"),
    )

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    service_id: Mapped[UUID | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    service_name: Mapped[str] = mapped_column(String(180))
    level: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(120))
    request_id: Mapped[str | None] = mapped_column(String(120))
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(message, ''))", persisted=True),
        nullable=True,
    )
