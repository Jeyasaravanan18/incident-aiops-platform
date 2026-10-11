"""AIOps Root-Cause Analysis, Remediation, and Postmortem Endpoints."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import get_llm_provider
from app.core.database import get_session
from app.core.errors import AppError
from app.models.alert import Alert
from app.models.incident import Incident
from app.models.log import LogEntry
from app.models.runbook import Runbook
from app.repositories.ai_repo import AIAnalysisRepository
from app.repositories.incident_repo import IncidentRepository
from app.repositories.service_repo import ServiceRepository
from app.schemas.ai import (
    AIAnalysisResponse,
    PostmortemDraftResponse,
    RemediationItem,
    RemediationRecommendationResponse,
)
from app.websocket.manager import websocket_manager

router = APIRouter(prefix="/ai", tags=["ai"])


async def collect_incident_context(incident: Incident, session: AsyncSession) -> dict[str, object]:
    """Gather multi-modal incident telemetry (alerts, logs, runbooks, history) from PostgreSQL."""
    service_name = "Unknown Service"
    if incident.service_id:
        svc = await ServiceRepository.get_by_id(session, incident.service_id)
        if svc:
            service_name = svc.name

    # 1. Fetch attached alerts
    alert_stmt = (
        select(Alert)
        .where(Alert.incident_id == incident.id)
        .order_by(Alert.last_seen.desc())
        .limit(50)
    )
    alerts = list(await session.scalars(alert_stmt))
    alert_dicts = [
        {
            "id": str(a.id),
            "title": a.title,
            "severity": a.severity.value if hasattr(a.severity, "value") else str(a.severity),
            "fingerprint": a.fingerprint,
            "source": a.source,
            "occurrence_count": a.occurrence_count,
        }
        for a in alerts
    ]

    # 2. Fetch logs within +/- 45 mins of incident detection
    det = incident.detected_at or incident.created_at or datetime.now(UTC)
    if det.tzinfo is None:
        det = det.replace(tzinfo=UTC)

    start_window = det - timedelta(minutes=45)
    end_window = det + timedelta(minutes=45)

    log_stmt = select(LogEntry).where(
        LogEntry.timestamp >= start_window, LogEntry.timestamp <= end_window
    )
    if incident.service_id:
        log_stmt = log_stmt.where(LogEntry.service_id == incident.service_id)
    log_stmt = log_stmt.order_by(LogEntry.timestamp.desc()).limit(30)
    logs = list(await session.scalars(log_stmt))

    log_dicts = [
        {
            "level": log_item.level,
            "message": log_item.message,
            "trace_id": log_item.trace_id,
            "request_id": log_item.request_id,
            "timestamp": log_item.timestamp.isoformat() if log_item.timestamp else "N/A",
        }
        for log_item in logs
    ]

    # 3. Fetch matching runbooks
    rb_stmt = select(Runbook)
    if incident.service_id:
        rb_stmt = rb_stmt.where(
            (Runbook.service_id == incident.service_id) | (Runbook.service_id.is_(None))
        )
    rb_stmt = rb_stmt.limit(20)
    runbooks = list(await session.scalars(rb_stmt))
    rb_dicts = [
        {
            "id": str(r.id),
            "title": r.title,
            "incident_type": r.incident_type,
            "body": r.body,
        }
        for r in runbooks
    ]

    # 4. Fetch historical resolved incidents for this service
    hist_stmt = select(Incident).where(
        Incident.id != incident.id,
        Incident.resolved_at.is_not(None),
    )
    if incident.service_id:
        hist_stmt = hist_stmt.where(Incident.service_id == incident.service_id)
    hist_stmt = hist_stmt.order_by(Incident.created_at.desc()).limit(5)
    hist_incidents = list(await session.scalars(hist_stmt))
    hist_dicts = [
        {
            "id": str(h.id),
            "title": h.title,
            "severity": h.severity.value if hasattr(h.severity, "value") else str(h.severity),
            "status": h.status.value if hasattr(h.status, "value") else str(h.status),
        }
        for h in hist_incidents
    ]

    return {
        "incident_id": str(incident.id),
        "title": incident.title,
        "description": incident.description or "",
        "severity": (
            incident.severity.value
            if hasattr(incident.severity, "value")
            else str(incident.severity)
        ),
        "status": (
            incident.status.value if hasattr(incident.status, "value") else str(incident.status)
        ),
        "service_name": service_name,
        "detected_at": det.isoformat(),
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else "N/A",
        "alerts": alert_dicts,
        "logs": log_dicts,
        "runbooks": rb_dicts,
        "history": hist_dicts,
    }


@router.post("/incidents/{incident_id}/analysis", response_model=AIAnalysisResponse)
async def analyze_incident(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> AIAnalysisResponse:
    incident = await IncidentRepository.get_by_id(session, incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    context = await collect_incident_context(incident, session)
    provider = get_llm_provider()
    result = await provider.analyze(context)

    provider_name = "gemini" if hasattr(provider, "api_key") else "heuristic-contextual"

    analysis = await AIAnalysisRepository.create_analysis(
        session,
        incident_id=incident.id,
        provider=provider_name,
        summary=result.summary,
        probable_causes=result.probable_causes,
        evidence=result.evidence,
        recommended_actions=result.recommended_actions,
        confidence=result.confidence,
        related_incidents=result.related_incidents,
    )

    await IncidentRepository.add_timeline_event(
        session,
        incident_id=incident.id,
        actor_id=None,
        event_type="AIAnalysisCompleted",
        message=f"AI analysis generated with {int(result.confidence * 100)}% confidence and {len(result.evidence)} evidence items.",
        metadata_json={
            "confidence": result.confidence,
            "causes_count": len(result.probable_causes),
        },
    )

    await websocket_manager.broadcast(
        f"incident:{incident.id}",
        {
            "type": "AIAnalysisCompleted",
            "incident_id": str(incident.id),
            "analysis_id": str(analysis.id),
            "confidence": result.confidence,
        },
    )

    return AIAnalysisResponse.model_validate(analysis)


@router.get("/incidents/{incident_id}/analysis", response_model=AIAnalysisResponse | None)
async def get_incident_analysis(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> AIAnalysisResponse | None:
    analysis = await AIAnalysisRepository.get_latest_by_incident_id(session, incident_id)
    if analysis is None:
        return None
    return AIAnalysisResponse.model_validate(analysis)


@router.post("/incidents/{incident_id}/postmortem-draft", response_model=PostmortemDraftResponse)
async def generate_postmortem_draft(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PostmortemDraftResponse:
    incident = await IncidentRepository.get_by_id(session, incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    context = await collect_incident_context(incident, session)
    provider = get_llm_provider()
    draft = await provider.draft_postmortem(context)

    return PostmortemDraftResponse(
        incident_id=incident.id,
        summary=draft.summary,
        impact=draft.impact,
        timeline=draft.timeline,
        root_cause=draft.root_cause,
        contributing_factors=draft.contributing_factors,
        resolution=draft.resolution,
        preventive_actions=draft.preventive_actions,
        lessons_learned=draft.lessons_learned,
    )


@router.post(
    "/incidents/{incident_id}/remediation", response_model=RemediationRecommendationResponse
)
async def recommend_remediation(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> RemediationRecommendationResponse:
    incident = await IncidentRepository.get_by_id(session, incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    context = await collect_incident_context(incident, session)
    provider = get_llm_provider()
    analysis = await provider.analyze(context)

    items = []
    for idx, act in enumerate(analysis.recommended_actions, start=1):
        items.append(
            RemediationItem(
                step=idx,
                title=f"Step {idx}",
                action=act,
                requires_approval=True,
                safe_to_automate=False,
                source_runbook="Runbook Catalog",
            )
        )

    return RemediationRecommendationResponse(
        incident_id=incident.id,
        recommended_actions=items,
        warning="SAFETY PROTOCOL: Automated execution disabled. All remediation actions require on-call engineer review and manual authorization.",
    )
