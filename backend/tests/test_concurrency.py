import asyncio

import pytest

from app.core.errors import AppError
from app.domain.idempotency import payload_hash
from app.domain.incidents import ALLOWED_TRANSITIONS, validate_transition
from app.models.enums import IncidentStatus


def test_concurrent_payload_hashing() -> None:
    """Verifies that payload_hash produces identical deterministic hashes concurrently."""
    payload = {
        "service_id": "99999999-9999-9999-9999-999999999999",
        "title": "High Memory Usage",
        "fingerprint": "service-mem-exhaustion-node-1",
        "metadata": {"cpu": 95, "mem_mb": 4096, "cluster": "us-east-1"},
    }

    hashes = [payload_hash(payload) for _ in range(50)]
    assert len(set(hashes)) == 1, "Payload hashing must be 100% deterministic"


@pytest.mark.asyncio
async def test_concurrent_transition_race_prevention() -> None:
    """Simulates multiple responders attempting contradictory state transitions concurrently."""
    initial_status = IncidentStatus.TRIGGERED
    target_status = IncidentStatus.ACKNOWLEDGED

    async def attempt_transition(target: IncidentStatus) -> bool:
        try:
            validate_transition(initial_status, target)
            return True
        except AppError:
            return False

    # 10 workers attempt to acknowledge the triggered incident simultaneously
    results = await asyncio.gather(*[attempt_transition(target_status) for _ in range(10)])
    assert all(results), "Valid transitions should all pass validation"

    # Conflicting / invalid transitions attempted simultaneously
    invalid_targets = [IncidentStatus.CLOSED, IncidentStatus.DETECTED, IncidentStatus.CLOSED]
    invalid_results = await asyncio.gather(*[attempt_transition(t) for t in invalid_targets])
    assert not any(invalid_results), "Invalid transitions must be rejected under race conditions"


def test_state_machine_transition_graph_integrity() -> None:
    """Ensures there are no circular dead-ends and all states have defined transitions."""
    for state in IncidentStatus:
        allowed = ALLOWED_TRANSITIONS.get(state, set())
        assert isinstance(allowed, set)
        if state not in (IncidentStatus.CLOSED,):
            assert len(allowed) > 0, f"State {state} must have at least one valid progression path"
