"""Runbook SOP Repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.runbook import Runbook


class RunbookRepository:
    @staticmethod
    async def list_runbooks(
        session: AsyncSession,
        service_id: UUID | None = None,
        incident_type: str | None = None,
    ) -> list[Runbook]:
        stmt = select(Runbook)
        if service_id is not None:
            stmt = stmt.where(Runbook.service_id == service_id)
        if incident_type is not None:
            stmt = stmt.where(Runbook.incident_type == incident_type)
        stmt = stmt.order_by(Runbook.title.asc())
        result = await session.scalars(stmt)
        return list(result.all())

    @staticmethod
    async def get_by_id(session: AsyncSession, runbook_id: UUID) -> Runbook | None:
        return await session.get(Runbook, runbook_id)

    @staticmethod
    async def create_runbook(session: AsyncSession, **kwargs) -> Runbook:
        rb = Runbook(**kwargs)
        session.add(rb)
        await session.flush()
        return rb

    @staticmethod
    async def update_runbook(session: AsyncSession, runbook: Runbook, updates: dict) -> Runbook:
        for k, v in updates.items():
            if hasattr(runbook, k):
                setattr(runbook, k, v)
        await session.flush()
        return runbook

    @staticmethod
    async def delete_runbook(session: AsyncSession, runbook: Runbook) -> None:
        await session.delete(runbook)
        await session.flush()
