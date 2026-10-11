from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class AIAnalysis(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ai_analyses"

    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(String(2000))
    probable_causes: Mapped[list] = mapped_column(JSONB, default=list)
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    recommended_actions: Mapped[list] = mapped_column(JSONB, default=list)
    confidence: Mapped[float] = mapped_column(default=0.0)
    related_incidents: Mapped[list] = mapped_column(JSONB, default=list)

    # RAG pipeline tracking and reproducibility audit fields
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    retrieved_chunk_ids: Mapped[list] = mapped_column(JSONB, default=list)
    chunk_scores: Mapped[dict] = mapped_column(JSONB, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    validity_flags: Mapped[dict] = mapped_column(JSONB, default=dict)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
