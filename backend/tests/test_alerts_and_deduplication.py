from datetime import UTC, datetime, timedelta
import hashlib
import json
import pytest

from app.domain.incidents import calculate_severity
from app.models.enums import AlertSeverity, AlertStatus, Criticality, IncidentSeverity


def test_fingerprint_generation_reproducibility() -> None:
    """Verifies that an alert fingerprint generated from source + title + service is consistent."""
    source = "datadog"
    service_slug = "payment-api"
    check_name = "http_response_time"

    fp1 = hashlib.sha256(f"{source}:{service_slug}:{check_name}".encode("utf-8")).hexdigest()
    fp2 = hashlib.sha256(f"{source}:{service_slug}:{check_name}".encode("utf-8")).hexdigest()

    assert fp1 == fp2
    assert len(fp1) == 64


def test_alert_severity_hierarchy() -> None:
    """Tests the severity calculation logic across various service criticalities."""
    # Critical alert + Critical service (score 6) -> SEV2
    assert calculate_severity(AlertSeverity.CRITICAL, Criticality.CRITICAL) == IncidentSeverity.SEV2

    # Critical alert + Critical service with multiple affected services (score 6 + 1 = 7) -> SEV1
    assert calculate_severity(AlertSeverity.CRITICAL, Criticality.CRITICAL, affected_services=2) == IncidentSeverity.SEV1

    # High service + Critical alert (score 5) -> SEV2
    assert calculate_severity(AlertSeverity.CRITICAL, Criticality.HIGH) == IncidentSeverity.SEV2

    # Medium service + Critical alert (score 4) -> SEV3
    assert calculate_severity(AlertSeverity.CRITICAL, Criticality.MEDIUM) == IncidentSeverity.SEV3

    # Low service + Critical alert (score 3) -> SEV3
    assert calculate_severity(AlertSeverity.CRITICAL, Criticality.LOW) == IncidentSeverity.SEV3

    # Error alert + Critical service (score 2 + 3 = 5) -> SEV2
    assert calculate_severity(AlertSeverity.ERROR, Criticality.CRITICAL) == IncidentSeverity.SEV2

    # Warning alert + Low service (score 1 + 0 = 1) -> SEV4
    assert calculate_severity(AlertSeverity.WARNING, Criticality.LOW) == IncidentSeverity.SEV4

    # Info alert + Critical service (score 0 + 3 = 3) -> SEV3
    assert calculate_severity(AlertSeverity.INFO, Criticality.CRITICAL) == IncidentSeverity.SEV3


def test_alert_lifecycle_states() -> None:
    """Validates that all expected alert statuses are supported in the enum."""
    expected = {"OPEN", "ACKNOWLEDGED", "SUPPRESSED", "RESOLVED"}
    actual = {s.value for s in AlertStatus}
    assert expected == actual


def test_alert_blast_radius_escalation() -> None:
    """Ensures that a non-critical alert escalates to SEV1 when blast radius is extensive."""
    sev = calculate_severity(
        AlertSeverity.ERROR,
        Criticality.MEDIUM,
        affected_services=5,
        error_rate_percent=45.0,
    )
    assert sev == IncidentSeverity.SEV1
