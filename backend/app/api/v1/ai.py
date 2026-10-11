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
from app.services.rag_generation import generate_grounded_analysis
from app.services.rag_retrieval import hybrid_retrieve
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

    service_name = "Unknown Service"
    if incident.service_id:
        svc = await ServiceRepository.get_by_id(session, incident.service_id)
        if svc:
            service_name = svc.name

    # 1. RAG Hybrid Retrieval (Dense Vector + Full-Text Search fused via RRF)
    search_query = f"{incident.title} {incident.description or ''}"
    retrieved_chunks = await hybrid_retrieve(
        session=session,
        query=search_query,
        service_id=incident.service_id,
        top_k=5,
    )

    # 2. Grounded Generation with Pydantic validation, retry, and citations
    rag_output, rag_meta = await generate_grounded_analysis(
        incident=incident,
        service_name=service_name,
        retrieved_chunks=retrieved_chunks,
    )

    evidence_items = [
        {
            "kind": "knowledge_chunk",
            "fact": c.content[:200],
            "chunk_id": str(c.id),
            "source_type": c.source_type,
        }
        for c in retrieved_chunks
        if c.id in rag_output.citations
    ]

    analysis = await AIAnalysisRepository.create_analysis(
        session,
        incident_id=incident.id,
        provider=rag_meta["model_name"],
        summary=rag_output.summary,
        probable_causes=rag_output.likely_causes,
        evidence=evidence_items,
        recommended_actions=rag_output.recommended_actions,
        confidence=rag_output.confidence,
        related_incidents=[str(c.source_id) for c in retrieved_chunks[:3]],
        model_name=rag_meta["model_name"],
        prompt_version=rag_meta["prompt_version"],
        retrieved_chunk_ids=rag_meta["retrieved_chunk_ids"],
        chunk_scores=rag_meta["chunk_scores"],
        latency_ms=rag_meta["latency_ms"],
        attempts=rag_meta["attempts"],
        validity_flags=rag_meta["validity_flags"],
        fallback_used=rag_meta["fallback_used"],
    )

    await IncidentRepository.add_timeline_event(
        session,
        incident_id=incident.id,
        actor_id=None,
        event_type="AIAnalysisCompleted",
        message=f"RAG AI analysis generated ({rag_meta['model_name']}) with {int(rag_output.confidence * 100)}% confidence and {len(rag_output.citations)} verified citations.",
        metadata_json={
            "confidence": rag_output.confidence,
            "causes_count": len(rag_output.likely_causes),
            "citations_count": len(rag_output.citations),
            "latency_ms": rag_meta["latency_ms"],
            "fallback_used": rag_meta["fallback_used"],
        },
    )

    await websocket_manager.broadcast(
        f"incident:{incident.id}",
        {
            "type": "AIAnalysisCompleted",
            "incident_id": str(incident.id),
            "analysis_id": str(analysis.id),
            "confidence": rag_output.confidence,
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
