import pytest

from app.core.errors import AppError
from app.domain.incidents import (
    calculate_severity,
    transition_timestamp_fields,
    validate_reopen,
    validate_transition,
)
from app.models.enums import AlertSeverity, Criticality, IncidentSeverity, IncidentStatus


def test_full_happy_path_incident_transitions() -> None:
    # DETECTED -> TRIGGERED
    validate_transition(IncidentStatus.DETECTED, IncidentStatus.TRIGGERED)

    # TRIGGERED -> ACKNOWLEDGED
    validate_transition(IncidentStatus.TRIGGERED, IncidentStatus.ACKNOWLEDGED)

    # ACKNOWLEDGED -> INVESTIGATING
    validate_transition(IncidentStatus.ACKNOWLEDGED, IncidentStatus.INVESTIGATING)

    # INVESTIGATING -> MITIGATING
    validate_transition(IncidentStatus.INVESTIGATING, IncidentStatus.MITIGATING)

    # MITIGATING -> RESOLVED
    validate_transition(IncidentStatus.MITIGATING, IncidentStatus.RESOLVED)

    # RESOLVED -> CLOSED
    validate_transition(IncidentStatus.RESOLVED, IncidentStatus.CLOSED)


def test_transition_timestamp_fields() -> None:
    ack_fields = transition_timestamp_fields(IncidentStatus.ACKNOWLEDGED)
    assert "acknowledged_at" in ack_fields

    res_fields = transition_timestamp_fields(IncidentStatus.RESOLVED)
    assert "resolved_at" in res_fields

    close_fields = transition_timestamp_fields(IncidentStatus.CLOSED)
    assert "closed_at" in close_fields

    inv_fields = transition_timestamp_fields(IncidentStatus.INVESTIGATING)
    assert inv_fields == {}


def test_reopen_validation() -> None:
    # Closed can be reopened
    validate_reopen(IncidentStatus.CLOSED)
    # Resolved can be reopened
    validate_reopen(IncidentStatus.RESOLVED)

    # Active incidents cannot be reopened
    with pytest.raises(AppError):
        validate_reopen(IncidentStatus.INVESTIGATING)

    with pytest.raises(AppError):
        validate_reopen(IncidentStatus.TRIGGERED)


def test_multi_factor_severity_calculation() -> None:
    # 1. Critical alert + Critical service + 3 services + 30% errors -> SEV1
    sev = calculate_severity(
        AlertSeverity.CRITICAL,
        Criticality.CRITICAL,
        affected_services=3,
        error_rate_percent=30,
    )
    assert sev == IncidentSeverity.SEV1

    # 2. Critical alert + High service + 1 service -> SEV2
    sev = calculate_severity(
        AlertSeverity.CRITICAL,
        Criticality.HIGH,
        affected_services=1,
    )
    assert sev == IncidentSeverity.SEV2

    # 3. Error alert + Medium service -> SEV3
    sev = calculate_severity(
        AlertSeverity.ERROR,
        Criticality.MEDIUM,
    )
    assert sev == IncidentSeverity.SEV3

    # 4. Info alert + Low service -> SEV4
    sev = calculate_severity(
        AlertSeverity.INFO,
        Criticality.LOW,
    )
    assert sev == IncidentSeverity.SEV4
