from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.ai.provider import get_llm_provider
from app.core.database import clean_doc, get_db
from app.core.errors import AppError
from app.schemas.ai import (
    AIAnalysisResponse,
    PostmortemDraftResponse,
    RemediationItem,
    RemediationRecommendationResponse,
)
from app.websocket.manager import websocket_manager

router = APIRouter(prefix="/ai", tags=["ai"])


async def collect_incident_context(
    incident: dict[str, Any], db: AsyncIOMotorDatabase
) -> dict[str, object]:
    sid = str(incident.get("service_id", ""))
    service = await db.services.find_one({"id": sid}) if sid else None
    service_name = service.get("name") if service else "Unknown Service"
    service_slug = service.get("slug") if service else ""

    # 1. Fetch attached alerts
    iid = str(incident["id"])
    alerts = await db.alerts.find({"incident_id": iid}).to_list(50)
    alert_dicts = [
        {
            "id": str(a.get("id")),
            "title": a.get("title"),
            "severity": str(a.get("severity")),
            "fingerprint": a.get("fingerprint"),
            "source": a.get("source"),
            "occurrence_count": a.get("occurrence_count", 1),
        }
        for a in alerts
    ]

    # 2. Fetch logs within +/- 45 mins of incident detection
    det = incident.get("detected_at") or incident.get("created_at") or datetime.now(UTC)
    if det.tzinfo is None:
        det = det.replace(tzinfo=UTC)

    start_window = det - timedelta(minutes=45)
    end_window = det + timedelta(minutes=45)

    logs_query: dict[str, Any] = {
        "$or": [
            {"service_id": sid},
            {"service_name": {"$regex": service_slug, "$options": "i"}},
            {"service_name": {"$regex": service_name, "$options": "i"}},
        ],
        "timestamp": {"$gte": start_window, "$lte": end_window},
    }
    logs = await db.logs.find(logs_query).sort("timestamp", -1).limit(30).to_list(30)
    log_dicts = [
        {
            "level": log_item.get("level"),
            "message": log_item.get("message"),
            "trace_id": log_item.get("trace_id"),
            "request_id": log_item.get("request_id"),
            "timestamp": (
                log_item.get("timestamp").isoformat() if log_item.get("timestamp") else "N/A"
            ),
        }
        for log_item in logs
    ]

    # 3. Fetch matching runbooks
    rb_query: dict[str, Any] = {"$or": [{"service_id": sid}, {"service_id": None}]}
    runbooks = await db.runbooks.find(rb_query).to_list(20)
    rb_dicts = [
        {
            "id": str(r.get("id")),
            "title": r.get("title"),
            "incident_type": r.get("incident_type"),
            "body": r.get("body"),
        }
        for r in runbooks
    ]

    # 4. Fetch historical resolved incidents for this service (RAG context)
    hist_query: dict[str, Any] = {
        "service_id": sid,
        "id": {"$ne": iid},
        "resolved_at": {"$ne": None},
    }
    hist_incidents = await db.incidents.find(hist_query).sort("created_at", -1).limit(5).to_list(5)
    hist_dicts = [
        {
            "id": str(h.get("id")),
            "title": h.get("title"),
            "severity": str(h.get("severity")),
            "status": str(h.get("status")),
        }
        for h in hist_incidents
    ]

    return {
        "incident_id": iid,
        "title": incident.get("title", ""),
        "description": incident.get("description", ""),
        "severity": str(incident.get("severity", "sev3")),
        "status": str(incident.get("status", "triggered")),
        "service_name": service_name,
        "detected_at": det.isoformat(),
        "resolved_at": (
            incident.get("resolved_at").isoformat() if incident.get("resolved_at") else "N/A"
        ),
        "alerts": alert_dicts,
        "logs": log_dicts,
        "runbooks": rb_dicts,
        "history": hist_dicts,
    }


@router.post("/incidents/{incident_id}/analysis", response_model=AIAnalysisResponse)
async def analyze_incident(
    incident_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> AIAnalysisResponse:
    iid = str(incident_id)
    incident = await db.incidents.find_one({"id": iid})
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    context = await collect_incident_context(incident, db)
    provider = get_llm_provider()
    result = await provider.analyze(context)

    analysis_id = str(uuid4())
    now = datetime.now(UTC)
    analysis_doc = {
        "id": analysis_id,
        "incident_id": iid,
        "provider": "gemini" if hasattr(provider, "api_key") else "heuristic-contextual",
        "summary": result.summary,
        "probable_causes": result.probable_causes,
        "evidence": result.evidence,
        "recommended_actions": result.recommended_actions,
        "confidence": result.confidence,
        "related_incidents": result.related_incidents,
        "created_at": now,
    }
    await db.ai_analyses.insert_one(analysis_doc)

    await db.timeline_events.insert_one(
        {
            "id": str(uuid4()),
            "incident_id": iid,
            "actor_id": None,
            "event_type": "AIAnalysisCompleted",
            "message": f"AI analysis generated with {int(result.confidence * 100)}% confidence and {len(result.evidence)} evidence items.",
            "metadata_json": {
                "confidence": result.confidence,
                "causes_count": len(result.probable_causes),
            },
            "created_at": now,
        }
    )

    await websocket_manager.broadcast(
        f"incident:{iid}",
        {
            "type": "AIAnalysisCompleted",
            "incident_id": iid,
            "analysis_id": analysis_id,
            "confidence": result.confidence,
        },
    )

    return AIAnalysisResponse(**clean_doc(analysis_doc))  # type: ignore


@router.get("/incidents/{incident_id}/analysis", response_model=AIAnalysisResponse | None)
async def get_incident_analysis(
    incident_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> AIAnalysisResponse | None:
    iid = str(incident_id)
    analysis = await db.ai_analyses.find_one({"incident_id": iid}, sort=[("created_at", -1)])
    if analysis is None:
        return None
    return AIAnalysisResponse(**clean_doc(analysis))  # type: ignore


@router.post("/incidents/{incident_id}/postmortem-draft", response_model=PostmortemDraftResponse)
async def generate_postmortem_draft(
    incident_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> PostmortemDraftResponse:
    iid = str(incident_id)
    incident = await db.incidents.find_one({"id": iid})
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    context = await collect_incident_context(incident, db)
    provider = get_llm_provider()
    draft = await provider.draft_postmortem(context)

    return PostmortemDraftResponse(
        incident_id=incident_id,
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
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> RemediationRecommendationResponse:
    iid = str(incident_id)
    incident = await db.incidents.find_one({"id": iid})
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident not found", 404)

    context = await collect_incident_context(incident, db)
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
        incident_id=incident_id,
        recommended_actions=items,
        warning="SAFETY PROTOCOL: Automated execution disabled. All remediation actions require on-call engineer review and manual authorization.",
    )
