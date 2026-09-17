from uuid import UUID

from pydantic import BaseModel


class MTTAMetric(BaseModel):
    mean_minutes: float
    count: int
    definition: str = "Mean Time To Acknowledge: acknowledged_at - detected_at (minutes)"


class MTTRMetric(BaseModel):
    mean_minutes: float
    median_minutes: float
    p95_minutes: float
    count: int
    definition: str = (
        "Mean Time To Resolve: resolved_at - detected_at (minutes). Mean, Median, and P95."
    )


class SeverityCount(BaseModel):
    severity: str
    count: int
    percentage: float


class ServiceIncidentCount(BaseModel):
    service_id: UUID
    service_name: str
    count: int
    sev1_count: int


class IncidentTrendPoint(BaseModel):
    date: str
    count: int
    sev1: int = 0
    sev2: int = 0
    sev3: int = 0
    sev4: int = 0


class ServiceReliabilityMetric(BaseModel):
    service_id: UUID
    service_name: str
    uptime_percentage: float
    total_checks: int
    avg_latency_ms: float | None


class RecurringPattern(BaseModel):
    pattern_key: str
    description: str
    occurrences: int
    affected_services: list[str]
    sample_incident_ids: list[UUID]


class AnalyticsSummaryResponse(BaseModel):
    total_incidents: int
    active_incidents: int
    resolved_incidents: int
    alert_count: int
    alert_to_incident_ratio: float
    mtta: MTTAMetric
    mttr: MTTRMetric
    severity_breakdown: list[SeverityCount]
    incidents_by_service: list[ServiceIncidentCount]
    incident_trends: list[IncidentTrendPoint]
    service_reliability: list[ServiceReliabilityMetric]
    recurring_patterns: list[RecurringPattern]
