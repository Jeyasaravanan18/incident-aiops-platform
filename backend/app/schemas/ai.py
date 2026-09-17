from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AIAnalysisEvidence(BaseModel):
    kind: str = Field(
        description="Kind of evidence: log, alert, metric, runbook, historical_incident"
    )
    fact: str
    source: str | None = None


class AIAnalysisResponse(BaseModel):
    id: UUID | None = None
    incident_id: UUID
    provider: str
    summary: str
    probable_causes: list[str]
    evidence: list[dict[str, str]]
    recommended_actions: list[str]
    confidence: float
    related_incidents: list[str]
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class PostmortemDraftResponse(BaseModel):
    incident_id: UUID
    summary: str
    impact: str
    timeline: str
    root_cause: str
    contributing_factors: str
    resolution: str
    preventive_actions: str
    lessons_learned: str


class RemediationItem(BaseModel):
    step: int
    title: str
    action: str
    requires_approval: bool = True
    safe_to_automate: bool = False
    source_runbook: str | None = None


class RemediationRecommendationResponse(BaseModel):
    incident_id: UUID
    recommended_actions: list[RemediationItem]
    warning: str = "Automated execution disabled. Human review and manual approval required."
