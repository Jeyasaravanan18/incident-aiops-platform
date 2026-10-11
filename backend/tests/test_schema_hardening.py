"""Unit and integration tests for Phase 2 schema hardening:

Validates CHECK constraints, GIN full-text indexes, partial indexes,
and server-side deterministic alert fingerprinting.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import app.models.all_models  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.domain.alerts import compute_alert_fingerprint
from app.models.alert import Alert
from app.models.enums import (
    AlertSeverity,
    Criticality,
    IncidentSeverity,
    IncidentStatus,
    ServiceStatus,
)
from app.models.incident import Incident
from app.models.log import LogEntry
from app.models.service import Service


def test_server_side_alert_fingerprint_normalization() -> None:
    """Verifies that server-side fingerprint is deterministic and collapses identical symptoms."""
    svc_id = uuid4()
    title_1 = "High HTTP 5xx Error Rate"
    title_2 = "  high http 5xx error rate  "

    meta_1 = {"cluster": "us-east-1", "code": "500", "latency_ms": 350}
    meta_2 = {"code": "500", "cluster": "us-east-1", "latency_ms": 9999}

    fp1 = compute_alert_fingerprint(svc_id, title_1, meta_1)
    fp2 = compute_alert_fingerprint(svc_id, title_2, meta_2)

    assert (
        fp1 == fp2
    ), "Fingerprints must match despite whitespace, casing, key order, and ignored latency"
    assert len(fp1) == 64


@pytest.mark.asyncio
async def test_incident_check_constraint_acknowledged_after_created() -> None:
    """Verifies that acknowledging before creation violates CHECK constraint ck_incidents_ack_after_created."""
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        svc = Service(
            name="Check Constraint Test Service",
            slug=f"check-test-{uuid4().hex[:8]}",
            status=ServiceStatus.HEALTHY,
            criticality=Criticality.MEDIUM,
        )
        session.add(svc)
        await session.flush()

        invalid_inc = Incident(
            service_id=svc.id,
            title="Invalid Timestamp Incident",
            status=IncidentStatus.ACKNOWLEDGED,
            severity=IncidentSeverity.SEV3,
            detected_at=now,
            created_at=now,
            acknowledged_at=now - timedelta(minutes=10),  # Violates constraint!
        )
        session.add(invalid_inc)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_alert_check_constraint_occurrence_count_positive() -> None:
    """Verifies that occurrence_count < 1 violates CHECK constraint ck_alerts_occurrence_count_positive."""
    async with AsyncSessionLocal() as session:
        svc = Service(
            name="Alert Check Test Service",
            slug=f"alert-check-{uuid4().hex[:8]}",
            status=ServiceStatus.HEALTHY,
            criticality=Criticality.LOW,
        )
        session.add(svc)
        await session.flush()

        invalid_alert = Alert(
            service_id=svc.id,
            source="prometheus",
            severity=AlertSeverity.WARNING,
            title="Zero Count Alert",
            fingerprint=f"zero-count-{uuid4().hex[:8]}",
            occurrence_count=0,  # Violates constraint!
        )
        session.add(invalid_alert)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_full_text_search_vector_generation_and_query() -> None:
    """Verifies that generated tsvector column automatically populates and matches full-text queries."""
    unique_keyword = f"catastrophic_{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as session:
        log = LogEntry(
            service_name="payment-api",
            level="CRITICAL",
            message=f"Critical outage encountered: {unique_keyword} memory failure occurred.",
            timestamp=datetime.now(UTC),
        )
        session.add(log)
        await session.commit()

        # Query using PostgreSQL full-text search against the generated search_vector
        stmt = text(
            "SELECT count(*) FROM log_entries WHERE search_vector @@ to_tsquery('english', :kw)"
        )
        result = await session.scalar(stmt, {"kw": unique_keyword})
        assert result >= 1, "Generated tsvector must index the message content"
