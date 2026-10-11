"""Postmortem Library Repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.postmortem import Postmortem


class PostmortemRepository:
    @staticmethod
    async def list_postmortems(
        session: AsyncSession, limit: int = 100, offset: int = 0
    ) -> list[Postmortem]:
        stmt = select(Postmortem).order_by(Postmortem.created_at.desc()).limit(limit).offset(offset)
        result = await session.scalars(stmt)
        return list(result.all())

    @staticmethod
    async def get_by_id(session: AsyncSession, postmortem_id: UUID) -> Postmortem | None:
        return await session.get(Postmortem, postmortem_id)

    @staticmethod
    async def get_by_incident_id(session: AsyncSession, incident_id: UUID) -> Postmortem | None:
        stmt = select(Postmortem).where(Postmortem.incident_id == incident_id)
        return await session.scalar(stmt)

    @staticmethod
    async def create_postmortem(session: AsyncSession, **kwargs) -> Postmortem:
        pm = Postmortem(**kwargs)
        session.add(pm)
        await session.flush()
        return pm

    @staticmethod
    async def update_postmortem(session: AsyncSession, pm: Postmortem, updates: dict) -> Postmortem:
        for k, v in updates.items():
            if hasattr(pm, k):
                setattr(pm, k, v)
        await session.flush()
        return pm
