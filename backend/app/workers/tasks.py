import asyncio
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import UUID

import httpx
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.domain.incidents import calculate_severity
from app.models.ai import AIAnalysis
from app.models.alert import Alert
from app.models.enums import AlertSeverity, AlertStatus, IncidentStatus, ServiceStatus
from app.models.incident import Incident, TimelineEvent
from app.models.postmortem import Postmortem
from app.models.runbook import Runbook
from app.models.service import Service, ServiceHealthCheck
from app.repositories.knowledge_repo import KnowledgeRepository
from app.services.rag_generation import generate_grounded_analysis
from app.services.rag_retrieval import hybrid_retrieve
from app.workers.celery_app import celery_app


async def _async_monitor_services() -> dict[str, object]:
    results = []
    async with SessionLocal() as session:
        stmt = select(Service).where(Service.health_endpoint.is_not(None))
        services = list(await session.scalars(stmt))

        async with httpx.AsyncClient(timeout=5.0) as client:
            for s in services:
                start = perf_counter()
                status_code = None
                available = False
                error_msg = None

                try:
                    resp = await client.get(str(s.health_endpoint))
                    status_code = resp.status_code
                    available = 200 <= status_code < 400
                except Exception as exc:
                    error_msg = f"{type(exc).__name__}: {str(exc)}"
                    available = False

                latency_ms = int((perf_counter() - start) * 1000)

                check = ServiceHealthCheck(
                    service_id=s.id,
                    http_status=status_code,
                    response_time_ms=latency_ms,
                    availability=available,
                    error=error_msg,
                )
                session.add(check)

                # Status update & alert generation on failure
                if not available:
                    s.status = (
                        ServiceStatus.DEGRADED
                        if (status_code and status_code < 500)
                        else ServiceStatus.UNHEALTHY
                    )
                    # Auto generate health check alert
                    fp = f"{s.slug}-health-check-failure"
                    existing_alert = await session.scalar(
                        select(Alert).where(
                            Alert.fingerprint == fp, Alert.status == AlertStatus.OPEN
                        )
                    )
                    if existing_alert:
                        existing_alert.occurrence_count += 1
                        existing_alert.last_seen = datetime.now(UTC)
                    else:
                        # Check for existing active incident
                        active_inc = await session.scalar(
                            select(Incident).where(
                                Incident.service_id == s.id,
                                Incident.status.in_(
                                    [
                                        IncidentStatus.DETECTED,
                                        IncidentStatus.TRIGGERED,
                                        IncidentStatus.ACKNOWLEDGED,
                                        IncidentStatus.INVESTIGATING,
                                        IncidentStatus.MITIGATING,
                                    ]
                                ),
                            )
                        )
                        inc_id = active_inc.id if active_inc else None
                        if not inc_id:
                            new_inc = Incident(
                                service_id=s.id,
                                title=f"{s.name} health check failure",
                                description=f"Automated health monitor detected failure on {s.health_endpoint}. Error: {error_msg or f'HTTP {status_code}'}",
                                status=IncidentStatus.TRIGGERED,
                                severity=calculate_severity(AlertSeverity.CRITICAL, s.criticality),
                                detected_at=datetime.now(UTC),
                            )
                            session.add(new_inc)
                            await session.flush()
                            inc_id = new_inc.id

                        alert = Alert(
                            service_id=s.id,
                            incident_id=inc_id,
                            source="health-monitor",
                            severity=AlertSeverity.CRITICAL,
                            title=f"{s.name} Health Check Degradation",
                            description=f"Health probe to {s.health_endpoint} failed. HTTP {status_code}: {error_msg or 'Timeout/Connection error'}",
                            fingerprint=fp,
                            metadata_json={"latency_ms": latency_ms, "status_code": status_code},
                        )
                        session.add(alert)
                else:
                    if s.status != ServiceStatus.HEALTHY:
                        # Only restore to healthy if no active critical alerts
                        active_alerts = await session.scalar(
                            select(Alert).where(
                                Alert.service_id == s.id,
                                Alert.status == AlertStatus.OPEN,
                                Alert.severity == AlertSeverity.CRITICAL,
                            )
                        )
                        if not active_alerts:
                            s.status = ServiceStatus.HEALTHY

                results.append(
                    {
                        "service": s.name,
                        "available": available,
                        "latency_ms": latency_ms,
                        "status_code": status_code,
                    }
                )

        await session.commit()
    return {"checked_count": len(results), "results": results}


async def _async_run_ai_analysis(incident_id: str) -> dict[str, object]:
    async with SessionLocal() as session:
        inc_uuid = UUID(incident_id)
        incident = await session.get(Incident, inc_uuid)
        if not incident:
            return {"status": "error", "message": "Incident not found"}

        service_name = "Unknown Service"
        if incident.service_id:
            svc = await session.get(Service, incident.service_id)
            if svc:
                service_name = svc.name

        # 1. RAG Hybrid Retrieval
        query = f"{incident.title} {incident.description or ''}"
        chunks = await hybrid_retrieve(
            session=session,
            query=query,
            service_id=incident.service_id,
            top_k=5,
        )

        # 2. Grounded Generation
        rag_output, rag_meta = await generate_grounded_analysis(
            incident=incident,
            service_name=service_name,
            retrieved_chunks=chunks,
        )

        evidence_items = [
            {
                "kind": "knowledge_chunk",
                "fact": c.content[:200],
                "chunk_id": str(c.id),
                "source_type": c.source_type,
            }
            for c in chunks
            if c.id in rag_output.citations
        ]

        analysis = AIAnalysis(
            incident_id=incident.id,
            provider=rag_meta["model_name"],
            summary=rag_output.summary,
            probable_causes=rag_output.likely_causes,
            evidence=evidence_items,
            recommended_actions=rag_output.recommended_actions,
            confidence=rag_output.confidence,
            related_incidents=[str(c.source_id) for c in chunks[:3]],
            model_name=rag_meta["model_name"],
            prompt_version=rag_meta["prompt_version"],
            retrieved_chunk_ids=rag_meta["retrieved_chunk_ids"],
            chunk_scores=rag_meta["chunk_scores"],
            latency_ms=rag_meta["latency_ms"],
            attempts=rag_meta["attempts"],
            validity_flags=rag_meta["validity_flags"],
            fallback_used=rag_meta["fallback_used"],
        )
        session.add(analysis)
        session.add(
            TimelineEvent(
                incident_id=incident.id,
                event_type="AIAnalysisCompleted",
                message=f"Background RAG AI analysis completed ({rag_meta['model_name']}). Confidence: {int(rag_output.confidence * 100)}%",
                metadata_json={
                    "provider": rag_meta["model_name"],
                    "citations_count": len(rag_output.citations),
                    "fallback_used": rag_meta["fallback_used"],
                },
            )
        )
        await session.commit()
        return {
            "status": "completed",
            "incident_id": incident_id,
            "confidence": rag_output.confidence,
            "fallback_used": rag_meta["fallback_used"],
        }


async def _async_reindex_knowledge_chunk(source_type: str, source_id_str: str) -> dict[str, object]:
    source_id = UUID(source_id_str)
    async with SessionLocal() as session:
        if source_type == "runbook":
            runbook = await session.get(Runbook, source_id)
            if runbook:
                content = f"{runbook.title}\nType: {runbook.incident_type}\n\n{runbook.body}"
                chunks = await KnowledgeRepository.index_document(
                    session=session,
                    source_type="runbook",
                    source_id=runbook.id,
                    service_id=runbook.service_id,
                    content=content,
                )
                await session.commit()
                return {"status": "indexed", "chunks": len(chunks)}
        elif source_type == "postmortem":
            pm = await session.get(Postmortem, source_id)
            if pm:
                content = (
                    f"Postmortem: {pm.title}\nRoot Cause: {pm.root_cause}\nSummary: {pm.summary}\n"
                    f"Resolution: {pm.resolution}\nAction Items: {pm.action_items}"
                )
                chunks = await KnowledgeRepository.index_document(
                    session=session,
                    source_type="postmortem",
                    source_id=pm.id,
                    service_id=pm.service_id,
                    content=content,
                )
                await session.commit()
                return {"status": "indexed", "chunks": len(chunks)}
    return {"status": "skipped"}


async def _async_cleanup_health_history() -> dict[str, object]:
    cutoff = datetime.now(UTC) - timedelta(days=settings.health_retention_days)
    async with SessionLocal() as session:
        result = await session.execute(
            delete(ServiceHealthCheck).where(ServiceHealthCheck.created_at < cutoff)
        )
        await session.commit()
        return {"deleted_checks": result.rowcount, "cutoff": cutoff.isoformat()}


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def monitor_services(self) -> dict[str, object]:
    return asyncio.run(_async_monitor_services())


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def run_ai_analysis(self, incident_id: str) -> dict[str, object]:
    return asyncio.run(_async_run_ai_analysis(incident_id))


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def reindex_knowledge_chunk(self, source_type: str, source_id: str) -> dict[str, object]:
    return asyncio.run(_async_reindex_knowledge_chunk(source_type, source_id))


@celery_app.task
def cleanup_health_history() -> dict[str, object]:
    return asyncio.run(_async_cleanup_history := _async_cleanup_health_history())
