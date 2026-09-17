from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class IdempotencyRecord(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (Index("ix_idempotency_key_scope", "key", "scope", unique=True),)

    key: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str] = mapped_column(String(120))
    request_hash: Mapped[str] = mapped_column(String(128))
    response_json: Mapped[dict] = mapped_column(JSONB, default=dict)
