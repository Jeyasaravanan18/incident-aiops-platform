"""AI Analysis Repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AIAnalysis


class AIAnalysisRepository:
    @staticmethod
    async def get_latest_by_incident_id(
        session: AsyncSession, incident_id: UUID
    ) -> AIAnalysis | None:
        stmt = (
            select(AIAnalysis)
            .where(AIAnalysis.incident_id == incident_id)
            .order_by(AIAnalysis.created_at.desc())
            .limit(1)
        )
        return await session.scalar(stmt)

    @staticmethod
    async def create_analysis(session: AsyncSession, **kwargs) -> AIAnalysis:
        analysis = AIAnalysis(**kwargs)
        session.add(analysis)
        await session.flush()
        return analysis
