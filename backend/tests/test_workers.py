from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

import app.models.all_models  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.models.ai import AIAnalysis
from app.models.enums import Criticality, IncidentSeverity, IncidentStatus, ServiceStatus
from app.models.incident import Incident
from app.models.service import Service
from app.workers.celery_app import celery_app
from app.workers.tasks import (
    _async_run_ai_analysis,
    cleanup_health_history,
    monitor_services,
    run_ai_analysis,
)


def test_celery_task_registration() -> None:
    assert monitor_services.name == "app.workers.tasks.monitor_services"
    assert run_ai_analysis.name == "app.workers.tasks.run_ai_analysis"
    assert cleanup_health_history.name == "app.workers.tasks.cleanup_health_history"


def test_celery_retry_configuration() -> None:
    # Auto retry for network and transient failures with exponential backoff
    assert monitor_services.autoretry_for == (Exception,)
    assert monitor_services.retry_backoff is True
    assert monitor_services.max_retries == 3


def test_celery_beat_schedule_configured() -> None:
    schedule = celery_app.conf.beat_schedule
    assert "monitor-services-every-30-seconds" in schedule
    assert schedule["monitor-services-every-30-seconds"]["schedule"] == 30.0
    assert "cleanup-health-history-daily" in schedule


@pytest.mark.asyncio
async def test_run_ai_analysis_worker_body() -> None:
    async with AsyncSessionLocal() as session:
        svc = Service(
            name="Worker Test Service",
            slug=f"worker-test-{uuid4().hex[:8]}",
            status=ServiceStatus.HEALTHY,
            criticality=Criticality.HIGH,
        )
        session.add(svc)
        await session.flush()

        inc = Incident(
            service_id=svc.id,
            title="Database Connection Latency Spike",
            description="Active pool queries timing out",
            status=IncidentStatus.TRIGGERED,
            severity=IncidentSeverity.SEV1,
            detected_at=datetime.now(UTC),
        )
        session.add(inc)
        await session.commit()
        inc_id = str(inc.id)

    res = await _async_run_ai_analysis(inc_id)
    assert res["status"] == "completed"
    assert res["incident_id"] == inc_id
    assert "confidence" in res

    async with AsyncSessionLocal() as session:
        analysis = await session.scalar(
            select(AIAnalysis).where(AIAnalysis.incident_id == UUID(inc_id))
        )
        assert analysis is not None
        assert analysis.provider == "celery-worker-heuristic"
        assert len(analysis.probable_causes) > 0
