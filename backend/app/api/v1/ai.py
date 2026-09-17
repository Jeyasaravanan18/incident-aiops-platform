from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import get_llm_provider
from app.core.database import get_session
from app.core.errors import AppError
from app.models.ai import AIAnalysis
from app.models.alert import Alert
from app.models.incident import Incident, TimelineEvent
from app.models.log import LogEntry
from app.models.runbook import Runbook
from app.models.service import Service
from app.schemas.ai import (
    AIAnalysisResponse,
    PostmortemDraftResponse,
    RemediationItem,
    RemediationRecommendationResponse,
)
from app.websocket.manager import websocket_manager

router = APIRouter(prefix="/ai", tags=["ai"])


async def collect_incident_context(incident: Incident, session: AsyncSession) -> dict[str, object]:
    service = await session.get(Service, incident.service_id)
    service_name = service.name if service else "Unknown Service"
    service_slug = service.slug if service else ""

    # 1. Fetch attached alerts
    alerts_stmt = select(Alert).where(Alert.incident_id == incident.id)
    alerts = list(await session.scalars(alerts_stmt))
    alert_dicts = [
        {
            "id": str(a.id),
            "title": a.title,
            "severity": str(a.severity),
            "fingerprint": a.fingerprint,
            "source": a.source,
            "occurrence_count": a.occurrence_count,
        }
        for a in alerts
    ]

    # 2. Fetch logs within +/- 45 mins of incident detection
    start_window = incident.detected_at - timedelta(minutes=45)
    end_window = incident.detected_at + timedelta(minutes=45)
    logs_stmt = (
        select(LogEntry)
        .where(
            or_(
                LogEntry.service_id == incident.service_id,
                LogEntry.service_name.ilike(f"%{service_slug}%"),
                LogEntry.service_name.ilike(f"%{service_name}%"),
            ),
            LogEntry.timestamp >= start_window,
            LogEntry.timestamp <= end_window,
        )
        .order_by(LogEntry.timestamp.desc())
        .limit(30)
    )
    logs = list(await session.scalars(logs_stmt))
    log_dicts = [
        {
            "level": log_entry.level,
            "message": log_entry.message,
            "trace_id": log_entry.trace_id,
            "request_id": log_entry.request_id,
            "timestamp": log_entry.timestamp.isoformat(),
        }
        for log_entry in logs
    ]

    # 3. Fetch matching runbooks
    rb_stmt = select(Runbook).where(
        or_(
            Runbook.service_id == incident.service_id,
            Runbook.service_id.is_(None),
        )
    )
    runbooks = list(await session.scalars(rb_stmt))
    rb_dicts = [
        {"id": str(r.id), "title": r.title, "incident_type": r.incident_type, "body": r.body}
        for r in runbooks
    ]

    # 4. Fetch historical resolved incidents for this service (RAG context)
    hist_stmt = (
        select(Incident)
        .where(
            Incident.service_id == incident.service_id,
            Incident.id != incident.id,
            Incident.resolved_at.is_not(None),
        )
        .order_by(Incident.created_at.desc())
        .limit(5)
    )
    hist_incidents = list(await session.scalars(hist_stmt))
    hist_dicts = [
        {"id": str(h.id), "title": h.title, "severity": str(h.severity), "status": str(h.status)}
        for h in hist_incidents
    ]

    return {
        "incident_id": str(incident.id),
        "title": incident.title,
        "description": incident.description,
        "severity": str(incident.severity),
        "status": str(incident.status),
        "service_name": service_name,
        "detected_at": incident.detected_at.isoformat() if incident.detected_at else "N/A",
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
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    context = await collect_incident_context(incident, session)
    provider = get_llm_provider()
    result = await provider.analyze(context)

    analysis = AIAnalysis(
        incident_id=incident.id,
        provider="heuristic-contextual",
        summary=result.summary,
        probable_causes=result.probable_causes,
        evidence=result.evidence,
        recommended_actions=result.recommended_actions,
        confidence=result.confidence,
        related_incidents=result.related_incidents,
    )
    session.add(analysis)

    session.add(
        TimelineEvent(
            incident_id=incident.id,
            event_type="AIAnalysisCompleted",
            message=f"AI analysis generated with {int(result.confidence * 100)}% confidence and {len(result.evidence)} evidence items.",
            metadata_json={
                "confidence": result.confidence,
                "causes_count": len(result.probable_causes),
            },
        )
    )
    await session.commit()
    await session.refresh(analysis)

    await websocket_manager.broadcast(
        f"incident:{incident.id}",
        {
            "type": "AIAnalysisCompleted",
            "incident_id": incident.id,
            "analysis_id": analysis.id,
            "confidence": result.confidence,
        },
    )

    return AIAnalysisResponse(
        id=analysis.id,
        incident_id=analysis.incident_id,
        provider=analysis.provider,
        summary=analysis.summary,
        probable_causes=analysis.probable_causes,
        evidence=analysis.evidence,
        recommended_actions=analysis.recommended_actions,
        confidence=analysis.confidence,
        related_incidents=analysis.related_incidents,
        created_at=analysis.created_at,
    )


@router.get("/incidents/{incident_id}/analysis", response_model=AIAnalysisResponse | None)
async def get_incident_analysis(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> AIAnalysisResponse | None:
    analysis = await session.scalar(
        select(AIAnalysis)
        .where(AIAnalysis.incident_id == incident_id)
        .order_by(AIAnalysis.created_at.desc())
    )
    if analysis is None:
        return None

    return AIAnalysisResponse(
        id=analysis.id,
        incident_id=analysis.incident_id,
        provider=analysis.provider,
        summary=analysis.summary,
        probable_causes=analysis.probable_causes,
        evidence=analysis.evidence,
        recommended_actions=analysis.recommended_actions,
        confidence=analysis.confidence,
        related_incidents=analysis.related_incidents,
        created_at=analysis.created_at,
    )


@router.post("/incidents/{incident_id}/postmortem-draft", response_model=PostmortemDraftResponse)
async def generate_postmortem_draft(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PostmortemDraftResponse:
    incident = await session.get(Incident, incident_id)
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
    incident = await session.get(Incident, incident_id)
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
