from datetime import UTC, datetime

from app.core.errors import AppError
from app.models.enums import AlertSeverity, Criticality, IncidentSeverity, IncidentStatus

ALLOWED_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.DETECTED: {IncidentStatus.TRIGGERED, IncidentStatus.ACKNOWLEDGED},
    IncidentStatus.TRIGGERED: {
        IncidentStatus.ACKNOWLEDGED,
        IncidentStatus.INVESTIGATING,
        IncidentStatus.MITIGATING,
        IncidentStatus.RESOLVED,
    },
    IncidentStatus.ACKNOWLEDGED: {
        IncidentStatus.INVESTIGATING,
        IncidentStatus.MITIGATING,
        IncidentStatus.RESOLVED,
    },
    IncidentStatus.INVESTIGATING: {
        IncidentStatus.MITIGATING,
        IncidentStatus.RESOLVED,
    },
    IncidentStatus.MITIGATING: {
        IncidentStatus.RESOLVED,
        IncidentStatus.INVESTIGATING,
    },
    IncidentStatus.RESOLVED: {
        IncidentStatus.CLOSED,
        IncidentStatus.INVESTIGATING,
    },
    IncidentStatus.CLOSED: set(),
}


def validate_transition(current: IncidentStatus, target: IncidentStatus) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise AppError(
            "INVALID_INCIDENT_TRANSITION",
            f"Cannot transition incident from {current} to {target}",
            status_code=409,
        )


def validate_reopen(current: IncidentStatus) -> None:
    if current not in {IncidentStatus.CLOSED, IncidentStatus.RESOLVED}:
        raise AppError(
            "INVALID_REOPEN_REQUEST",
            f"Only CLOSED or RESOLVED incidents can be reopened; current status is {current}",
            status_code=409,
        )


def transition_timestamp_fields(target: IncidentStatus) -> dict[str, datetime]:
    now = datetime.now(UTC)
    if target == IncidentStatus.ACKNOWLEDGED:
        return {"acknowledged_at": now}
    if target == IncidentStatus.RESOLVED:
        return {"resolved_at": now}
    if target == IncidentStatus.CLOSED:
        return {"closed_at": now}
    return {}


def calculate_severity(
    alert_severity: AlertSeverity,
    service_criticality: Criticality,
    affected_services: int = 1,
    error_rate_percent: float = 0,
) -> IncidentSeverity:
    score = 0
    score += {
        AlertSeverity.INFO: 0,
        AlertSeverity.WARNING: 1,
        AlertSeverity.ERROR: 2,
        AlertSeverity.CRITICAL: 3,
    }[alert_severity]
    score += {
        Criticality.LOW: 0,
        Criticality.MEDIUM: 1,
        Criticality.HIGH: 2,
        Criticality.CRITICAL: 3,
    }[service_criticality]
    if affected_services >= 3:
        score += 2
    elif affected_services == 2:
        score += 1
    if error_rate_percent >= 25:
        score += 2
    elif error_rate_percent >= 10:
        score += 1

    if score >= 7:
        return IncidentSeverity.SEV1
    if score >= 5:
        return IncidentSeverity.SEV2
    if score >= 3:
        return IncidentSeverity.SEV3
    return IncidentSeverity.SEV4
