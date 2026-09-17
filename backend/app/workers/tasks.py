import asyncio
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import UUID

import httpx
from sqlalchemy import delete, select

from app.ai.provider import get_llm_provider
from app.core.config import settings
from app.core.database import SessionLocal
from app.domain.incidents import calculate_severity
from app.models.ai import AIAnalysis
from app.models.alert import Alert
from app.models.enums import AlertSeverity, AlertStatus, IncidentStatus, ServiceStatus
from app.models.incident import Incident, TimelineEvent
from app.models.service import Service, ServiceHealthCheck
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

        from app.api.v1.ai import collect_incident_context

        context = await collect_incident_context(incident, session)
        provider = get_llm_provider()
        res = await provider.analyze(context)

        analysis = AIAnalysis(
            incident_id=incident.id,
            provider="celery-worker-heuristic",
            summary=res.summary,
            probable_causes=res.probable_causes,
            evidence=res.evidence,
            recommended_actions=res.recommended_actions,
            confidence=res.confidence,
            related_incidents=res.related_incidents,
        )
        session.add(analysis)
        session.add(
            TimelineEvent(
                incident_id=incident.id,
                event_type="AIAnalysisCompleted",
                message=f"Background AI analysis completed. Confidence: {int(res.confidence * 100)}%",
                metadata_json={"provider": "celery-worker"},
            )
        )
        await session.commit()
        return {"status": "completed", "incident_id": incident_id, "confidence": res.confidence}


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


@celery_app.task
def cleanup_health_history() -> dict[str, object]:
    return asyncio.run(_async_cleanup_health_history())
