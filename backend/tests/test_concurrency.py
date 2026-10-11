"""Real concurrency tests against PostgreSQL.

Validates:
1. 50 concurrent ingestions of the exact same alert collapse to 1 row with occurrence_count == 50.
2. 20 concurrent alerts for one service during an alert storm create exactly 1 open incident via pg_advisory_xact_lock.
3. 2 concurrent conflicting transitions on an incident result in exactly one 200 and one 409 via SELECT ... FOR UPDATE.
4. Idempotency keys stored in PostgreSQL return cached response on replay and reject payload mismatch with 409.
"""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token
from app.domain.idempotency import payload_hash
from app.main import app
from app.models.alert import Alert
from app.models.enums import (
    Criticality,
    IncidentSeverity,
    IncidentStatus,
    Role,
    ServiceStatus,
)
from app.models.idempotency import IdempotencyRecord
from app.models.incident import Incident
from app.models.service import Service
from app.models.user import User
from app.schemas.alert import AlertCreate


@pytest.mark.asyncio
async def test_concurrent_alert_ingestion_deduplication() -> None:
    """Verifies that 50 concurrent ingestions of the exact same alert
    collapse into exactly 1 database row with occurrence_count == 50 via
    atomic INSERT ... ON CONFLICT (fingerprint) DO UPDATE.
    """
    slug = f"dedup-test-{uuid4().hex[:8]}"
    async with AsyncSessionLocal() as session:
        svc = Service(
            name="Dedup Test Service",
            slug=slug,
            status=ServiceStatus.HEALTHY,
            criticality=Criticality.HIGH,
        )
        session.add(svc)
        await session.commit()
        svc_id = svc.id

    payload = {
        "service_id": str(svc_id),
        "source": "datadog",
        "severity": "CRITICAL",
        "title": "Database Connection Pool Exhausted",
        "description": "Active pool usage exceeded 95%",
        "metadata": {"cluster": "us-east-1", "pool": "writer"},
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Launch 50 concurrent ingestion HTTP requests
        tasks = [client.post("/api/v1/alerts", json=payload) for _ in range(50)]
        responses = await asyncio.gather(*tasks)

    for r in responses:
        assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"

    # Verify directly in PostgreSQL
    async with AsyncSessionLocal() as session:
        stmt = select(Alert).where(Alert.service_id == svc_id)
        alerts = (await session.scalars(stmt)).all()

        assert len(alerts) == 1, f"Expected exactly 1 alert row, found {len(alerts)}"
        assert (
            alerts[0].occurrence_count == 50
        ), f"Expected occurrence_count == 50, got {alerts[0].occurrence_count}"


@pytest.mark.asyncio
async def test_concurrent_alert_storm_creates_single_incident() -> None:
    """Verifies that 20 distinct concurrent alerts hitting the same service
    during an alert storm create exactly 1 open incident via pg_advisory_xact_lock
    and correlate all 20 alerts to that same incident.
    """
    slug = f"storm-test-{uuid4().hex[:8]}"
    async with AsyncSessionLocal() as session:
        svc = Service(
            name="Alert Storm Service",
            slug=slug,
            status=ServiceStatus.HEALTHY,
            criticality=Criticality.HIGH,
        )
        session.add(svc)
        await session.commit()
        svc_id = svc.id

    # 20 distinct alerts for the same service
    payloads = [
        {
            "service_id": str(svc_id),
            "source": "prometheus",
            "severity": "WARNING",
            "title": f"Service Alert Storm #{i}",
            "description": f"Storm alert sequence {i}",
            "metadata": {"storm_seq": i},
        }
        for i in range(20)
    ]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        tasks = [client.post("/api/v1/alerts", json=p) for p in payloads]
        responses = await asyncio.gather(*tasks)

    for r in responses:
        assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"

    # Verify directly in PostgreSQL
    async with AsyncSessionLocal() as session:
        inc_stmt = select(Incident).where(
            Incident.service_id == svc_id,
            Incident.status.notin_([IncidentStatus.RESOLVED, IncidentStatus.CLOSED]),
        )
        incidents = (await session.scalars(inc_stmt)).all()
        assert (
            len(incidents) == 1
        ), f"Expected exactly 1 open incident from alert storm, found {len(incidents)}"

        open_incident = incidents[0]
        alert_stmt = select(Alert).where(Alert.service_id == svc_id)
        alerts = (await session.scalars(alert_stmt)).all()
        assert len(alerts) == 20, f"Expected 20 alerts, found {len(alerts)}"
        for a in alerts:
            assert (
                a.incident_id == open_incident.id
            ), f"Alert {a.id} not correlated to incident {open_incident.id}"


@pytest.mark.asyncio
async def test_concurrent_conflicting_transitions() -> None:
    """Verifies that 2 concurrent conflicting status transitions on an incident
    result in exactly one 200 OK and one 409 Conflict via SELECT ... FOR UPDATE.
    """
    slug = f"trans-test-{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        user = User(
            email=f"eng-{uuid4().hex[:8]}@example.com",
            full_name="Concurrency Engineer",
            password_hash="test-hash",
            role=Role.ENGINEER,
            is_active=True,
        )
        session.add(user)
        await session.flush()

        svc = Service(
            name="Transition Race Service",
            slug=slug,
            status=ServiceStatus.HEALTHY,
            criticality=Criticality.MEDIUM,
        )
        session.add(svc)
        await session.flush()

        incident = Incident(
            service_id=svc.id,
            title="State Machine Concurrency Test",
            description="Testing concurrent transition race conditions",
            severity=IncidentSeverity.SEV2,
            status=IncidentStatus.TRIGGERED,
            detected_at=now,
        )
        session.add(incident)
        await session.commit()
        inc_id = incident.id
        user_id = user.id
        user_role = user.role.value

    token = create_access_token(user_id=user_id, role=user_role)
    headers = {"Authorization": f"Bearer {token}"}

    # Both responders concurrently attempt to transition the incident
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        tasks = [
            client.post(
                f"/api/v1/incidents/{inc_id}/transition",
                json={"status": "ACKNOWLEDGED", "reason": "Responder 1 claiming"},
                headers=headers,
            ),
            client.post(
                f"/api/v1/incidents/{inc_id}/transition",
                json={"status": "ACKNOWLEDGED", "reason": "Responder 2 claiming"},
                headers=headers,
            ),
        ]
        responses = await asyncio.gather(*tasks)

    status_codes = [r.status_code for r in responses]
    assert 200 in status_codes, f"Expected one 200 OK, got: {status_codes}"
    assert 409 in status_codes, f"Expected one 409 Conflict, got: {status_codes}"
    assert status_codes.count(200) == 1
    assert status_codes.count(409) == 1

    # Verify incident state in PostgreSQL is ACKNOWLEDGED
    async with AsyncSessionLocal() as session:
        reloaded = await session.get(Incident, inc_id)
        assert reloaded is not None
        assert reloaded.status == IncidentStatus.ACKNOWLEDGED
        assert reloaded.acknowledged_at is not None


@pytest.mark.asyncio
async def test_idempotency_stored_and_replayed() -> None:
    """Verifies that requests with an Idempotency-Key return the cached response on replay
    and reject mismatched payloads with 409 Conflict.
    """
    slug = f"idemp-test-{uuid4().hex[:8]}"
    async with AsyncSessionLocal() as session:
        svc = Service(
            name="Idempotency Test Service",
            slug=slug,
            status=ServiceStatus.HEALTHY,
            criticality=Criticality.LOW,
        )
        session.add(svc)
        await session.commit()
        svc_id = svc.id

    idemp_key = f"key-{uuid4()}"
    headers = {"Idempotency-Key": idemp_key}
    payload_a = {
        "service_id": str(svc_id),
        "source": "prometheus",
        "severity": "WARNING",
        "title": "Idempotent Alert Submission",
        "description": "Original submission payload",
        "metadata": {"check": "disk_space"},
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First execution -> 201 Created
        resp1 = await client.post("/api/v1/alerts", json=payload_a, headers=headers)
        assert resp1.status_code == 201
        data1 = resp1.json()

        # Replay with same key and same payload -> returns cached response (201)
        resp2 = await client.post("/api/v1/alerts", json=payload_a, headers=headers)
        assert resp2.status_code == 201
        data2 = resp2.json()
        assert data1["id"] == data2["id"]

        # Replay with same key but DIFFERENT payload -> 409 Conflict
        payload_b = {**payload_a, "title": "Tampered Alert Submission"}
        resp3 = await client.post("/api/v1/alerts", json=payload_b, headers=headers)
        assert resp3.status_code == 409
        err = resp3.json()
        assert err["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    # Verify IdempotencyRecord exists in PostgreSQL with unique constraint
    async with AsyncSessionLocal() as session:
        stmt = select(IdempotencyRecord).where(IdempotencyRecord.key == idemp_key)
        record = await session.scalar(stmt)
        assert record is not None
        assert record.scope == "alert_ingest"
        expected_hash = payload_hash(AlertCreate(**payload_a).model_dump())
        assert record.request_hash == expected_hash
