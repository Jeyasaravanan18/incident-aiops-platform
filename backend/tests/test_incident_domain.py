import pytest

from app.core.errors import AppError
from app.domain.incidents import calculate_severity, validate_transition
from app.models.enums import AlertSeverity, Criticality, IncidentSeverity, IncidentStatus


def test_severity_uses_alert_and_service_criticality() -> None:
    severity = calculate_severity(
        AlertSeverity.CRITICAL,
        Criticality.CRITICAL,
        affected_services=2,
        error_rate_percent=12,
    )
    assert severity == IncidentSeverity.SEV1


def test_low_impact_incident_is_sev4() -> None:
    assert calculate_severity(AlertSeverity.INFO, Criticality.LOW) == IncidentSeverity.SEV4


def test_valid_incident_transition() -> None:
    validate_transition(IncidentStatus.TRIGGERED, IncidentStatus.ACKNOWLEDGED)


def test_invalid_incident_transition_is_rejected() -> None:
    with pytest.raises(AppError):
        validate_transition(IncidentStatus.CLOSED, IncidentStatus.INVESTIGATING)
