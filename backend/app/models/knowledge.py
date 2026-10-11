"""Knowledge Chunk model for RAG hybrid search over past postmortems, runbooks, incidents, and logs."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class KnowledgeChunk(UUIDMixin, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index("ix_knowledge_chunks_source", "source_type", "source_id"),
        Index("ix_knowledge_chunks_service_id", "service_id"),
        Index("ix_knowledge_chunks_search_vector_gin", "search_vector", postgresql_using="gin"),
    )

    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    service_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Stored as JSONB list of floats or pgvector
    embedding: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(content, ''))", persisted=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
