from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Runbook(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "runbooks"

    service_id: Mapped[UUID | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(240))
    incident_type: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
