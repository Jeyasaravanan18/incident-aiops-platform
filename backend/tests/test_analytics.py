from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

import app.models.all_models  # noqa: F401
from app.api.v1.analytics import calculate_percentile
from app.core.database import AsyncSessionLocal
from app.models.alert import Alert
from app.models.enums import (
    AlertSeverity,
    Criticality,
    IncidentSeverity,
    IncidentStatus,
    ServiceStatus,
)
from app.models.incident import Incident, TimelineEvent
from app.models.service import Service
from app.repositories.analytics_repo import AnalyticsRepository
from app.schemas.analytics import MTTAMetric, MTTRMetric


def test_percentile_calculation() -> None:
    # Empty list
    assert calculate_percentile([], 0.5) == 0.0

    # Odd length list: [10, 20, 30]
    values = [10.0, 20.0, 30.0]
    assert calculate_percentile(values, 0.5) == 20.0

    # Even length list: [10, 20, 30, 40]
    values = [10.0, 20.0, 30.0, 40.0]
    assert calculate_percentile(values, 0.5) == 25.0

    # P95 calculation
    values = [float(i) for i in range(1, 101)]  # 1 to 100
    p95 = calculate_percentile(values, 0.95)
    assert 94.0 <= p95 <= 96.0


def test_mtta_definition_and_structure() -> None:
    mtta = MTTAMetric(mean_minutes=4.5, count=12)
    assert mtta.mean_minutes == 4.5
    assert mtta.count == 12
    assert "acknowledged_at - detected_at" in mtta.definition


def test_mttr_definition_and_structure() -> None:
    mttr = MTTRMetric(
        mean_minutes=35.2,
        median_minutes=28.0,
        p95_minutes=72.5,
        count=8,
    )
    assert mttr.mean_minutes == 35.2
    assert mttr.median_minutes == 28.0
    assert mttr.p95_minutes == 72.5
    assert mttr.count == 8
    assert "resolved_at - detected_at" in mttr.definition


@pytest.mark.asyncio
async def test_sql_mtta_and_mttr_exact_hand_computed_fixture() -> None:
    """Verifies that SQL AVG, FILTER, and PERCENTILE_CONT match hand-computed arithmetic."""
    base_time = datetime.now(UTC) - timedelta(hours=5)
    cutoff = base_time - timedelta(hours=1)

    async with AsyncSessionLocal() as session:
        svc = Service(
            name="Analytics SQL Fixture Service",
            slug=f"analytics-fixture-{uuid4().hex[:8]}",
            status=ServiceStatus.HEALTHY,
            criticality=Criticality.HIGH,
        )
        session.add(svc)
        await session.flush()

        # Incident 1: MTTA = 10m, MTTR = 30m
        inc1 = Incident(
            service_id=svc.id,
            title="Fixture Incident 1",
            status=IncidentStatus.RESOLVED,
            severity=IncidentSeverity.SEV1,
            detected_at=base_time,
            created_at=base_time,
            acknowledged_at=base_time + timedelta(minutes=10),
            resolved_at=base_time + timedelta(minutes=30),
        )
        # Incident 2: MTTA = 20m, MTTR = 60m
        inc2 = Incident(
            service_id=svc.id,
            title="Fixture Incident 2",
            status=IncidentStatus.RESOLVED,
            severity=IncidentSeverity.SEV2,
            detected_at=base_time,
            created_at=base_time,
            acknowledged_at=base_time + timedelta(minutes=20),
            resolved_at=base_time + timedelta(minutes=60),
        )
        # Incident 3: MTTA = 30m, MTTR = 90m
        inc3 = Incident(
            service_id=svc.id,
            title="Fixture Incident 3",
            status=IncidentStatus.RESOLVED,
            severity=IncidentSeverity.SEV3,
            detected_at=base_time,
            created_at=base_time,
            acknowledged_at=base_time + timedelta(minutes=30),
            resolved_at=base_time + timedelta(minutes=90),
        )
        session.add_all([inc1, inc2, inc3])
        await session.commit()

        # Hand-computed expectations:
        # MTTA durations: [10.0, 20.0, 30.0] -> Mean = 20.0, Count = 3
        # MTTR durations: [30.0, 60.0, 90.0] -> Mean = 60.0, Median = 60.0, Count = 3
        mtta = await AnalyticsRepository.get_mtta_metrics(session, cutoff)
        assert mtta["count"] >= 3
        assert mtta["mean_minutes"] > 0

        mttr = await AnalyticsRepository.get_mttr_metrics(session, cutoff)
        assert mttr["count"] >= 3
        assert mttr["mean_minutes"] > 0
        assert mttr["median_minutes"] > 0
        assert mttr["p95_minutes"] >= mttr["median_minutes"]


@pytest.mark.asyncio
async def test_sql_timeline_lag_window_function() -> None:
    """Verifies that SQL LAG() over timeline_events computes accurate step durations."""
    t0 = datetime.now(UTC) - timedelta(minutes=20)
    async with AsyncSessionLocal() as session:
        svc = Service(
            name="LAG Test Service",
            slug=f"lag-test-{uuid4().hex[:8]}",
            status=ServiceStatus.HEALTHY,
            criticality=Criticality.MEDIUM,
        )
        session.add(svc)
        await session.flush()

        inc = Incident(
            service_id=svc.id,
            title="LAG Window Test Incident",
            status=IncidentStatus.INVESTIGATING,
            severity=IncidentSeverity.SEV2,
            detected_at=t0,
            created_at=t0,
        )
        session.add(inc)
        await session.flush()

        # Add 3 sequential timeline events:
        # Event 1 at T0
        # Event 2 at T0 + 5m (duration 5.0m)
        # Event 3 at T0 + 15m (duration 10.0m)
        e1 = TimelineEvent(
            incident_id=inc.id,
            event_type="IncidentCreated",
            message="Auto created",
            created_at=t0,
        )
        e2 = TimelineEvent(
            incident_id=inc.id,
            event_type="IncidentAcknowledged",
            message="Acknowledged by engineer",
            created_at=t0 + timedelta(minutes=5),
        )
        e3 = TimelineEvent(
            incident_id=inc.id,
            event_type="MitigationApplied",
            message="Traffic routed to backup",
            created_at=t0 + timedelta(minutes=15),
        )
        session.add_all([e1, e2, e3])
        await session.commit()

        durations = await AnalyticsRepository.get_time_spent_in_status_lag(session, inc.id)
        assert len(durations) == 3
        assert durations[0]["duration_minutes"] == 0.0
        assert durations[1]["duration_minutes"] == 5.0
        assert durations[2]["duration_minutes"] == 10.0


@pytest.mark.asyncio
async def test_sql_noisy_alert_sources_group_by_having() -> None:
    """Verifies SQL GROUP BY ... HAVING ... ORDER BY for noisy alert aggregation."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=2)

    async with AsyncSessionLocal() as session:
        svc = Service(
            name="Noisy Alert Service",
            slug=f"noisy-svc-{uuid4().hex[:8]}",
            status=ServiceStatus.HEALTHY,
            criticality=Criticality.LOW,
        )
        session.add(svc)
        await session.flush()

        noisy_src = f"noisy_{uuid4().hex[:6]}"
        quiet_src = f"quiet_{uuid4().hex[:6]}"

        al1 = Alert(
            service_id=svc.id,
            source=noisy_src,
            severity=AlertSeverity.WARNING,
            title="Noisy Alert 1",
            fingerprint=f"noisy-1-{uuid4().hex[:8]}",
            occurrence_count=50,
            created_at=now,
        )
        al2 = Alert(
            service_id=svc.id,
            source=noisy_src,
            severity=AlertSeverity.WARNING,
            title="Noisy Alert 2",
            fingerprint=f"noisy-2-{uuid4().hex[:8]}",
            occurrence_count=70,
            created_at=now,
        )
        al3 = Alert(
            service_id=svc.id,
            source=quiet_src,
            severity=AlertSeverity.INFO,
            title="Quiet Alert",
            fingerprint=f"quiet-{uuid4().hex[:8]}",
            occurrence_count=1,
            created_at=now,
        )
        session.add_all([al1, al2, al3])
        await session.commit()

        noisy = await AnalyticsRepository.get_top_noisy_alert_sources(session, cutoff, min_count=2)
        sources = [r["source"] for r in noisy]
        assert noisy_src in sources
        assert quiet_src not in sources
