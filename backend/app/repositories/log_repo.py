"""Structured Log Repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import LogEntry


class LogRepository:
    @staticmethod
    async def create_log(
        session: AsyncSession,
        timestamp: datetime,
        service_id: UUID | None,
        service_name: str,
        level: str,
        message: str,
        trace_id: str | None = None,
        request_id: str | None = None,
        metadata_json: dict | None = None,
    ) -> LogEntry:
        entry = LogEntry(
            timestamp=timestamp,
            service_id=service_id,
            service_name=service_name,
            level=level.upper(),
            message=message,
            trace_id=trace_id,
            request_id=request_id,
            metadata_json=metadata_json or {},
        )
        session.add(entry)
        await session.flush()
        return entry

    @staticmethod
    async def list_logs(
        session: AsyncSession,
        service: str | None = None,
        level: str | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
        search: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LogEntry]:
        stmt = select(LogEntry)
        if service:
            stmt = stmt.where(func.lower(LogEntry.service_name).contains(service.lower()))
        if level:
            stmt = stmt.where(LogEntry.level == level.upper())
        if trace_id:
            stmt = stmt.where(LogEntry.trace_id == trace_id)
        if request_id:
            stmt = stmt.where(LogEntry.request_id == request_id)
        if search:
            stmt = stmt.where(func.lower(LogEntry.message).contains(search.lower()))
        if start_time:
            stmt = stmt.where(LogEntry.timestamp >= start_time)
        if end_time:
            stmt = stmt.where(LogEntry.timestamp <= end_time)

        stmt = stmt.order_by(LogEntry.timestamp.desc()).limit(limit).offset(offset)
        result = await session.scalars(stmt)
        return list(result.all())
