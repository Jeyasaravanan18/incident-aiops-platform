from sqlalchemy import Computed, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Runbook(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "runbooks"
    __table_args__ = (
        Index("ix_runbooks_search_vector_gin", "search_vector", postgresql_using="gin"),
    )

    service_id: Mapped[UUID | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(240))
    incident_type: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body, ''))",
            persisted=True,
        ),
        nullable=True,
    )
