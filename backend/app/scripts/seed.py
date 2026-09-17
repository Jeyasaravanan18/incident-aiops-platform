import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.ai import AIAnalysis
from app.models.alert import Alert
from app.models.enums import (
    AlertSeverity,
    AlertStatus,
    Criticality,
    IncidentSeverity,
    IncidentStatus,
    Role,
    ServiceStatus,
)
from app.models.idempotency import IdempotencyRecord
from app.models.incident import (
    Incident,
    IncidentAssignment,
    IncidentComment,
    TimelineEvent,
)
from app.models.log import LogEntry
from app.models.notification import Notification
from app.models.postmortem import Postmortem
from app.models.runbook import Runbook
from app.models.service import Service, ServiceHealthCheck
from app.models.user import RefreshToken, User


async def seed() -> None:
    async with SessionLocal() as session:
        # Check if already seeded
        existing = await session.scalar(select(User).where(User.email == "admin@example.com"))
        if existing is not None:
            print("Database already seeded. Cleaning and re-seeding for fresh scenario...")
            # Clean up all tables in reverse dependency order for idempotency
            await session.execute(delete(AIAnalysis))
            await session.execute(delete(Postmortem))
            await session.execute(delete(TimelineEvent))
            await session.execute(delete(IncidentComment))
            await session.execute(delete(IncidentAssignment))
            await session.execute(delete(Alert))
            await session.execute(delete(Incident))
            await session.execute(delete(LogEntry))
            await session.execute(delete(ServiceHealthCheck))
            await session.execute(delete(Runbook))
            await session.execute(delete(Service))
            await session.execute(delete(Notification))
            await session.execute(delete(IdempotencyRecord))
            await session.execute(delete(RefreshToken))
            await session.execute(delete(User))
            await session.commit()

        print("Seeding users...")
        now = datetime.now(UTC)
        admin = User(
            email="admin@example.com",
            full_name="Avery Morgan (Admin)",
            password_hash=hash_password("ChangeMe123!"),
            role=Role.ADMIN,
        )
        engineer = User(
            email="engineer@example.com",
            full_name="Riya Shah (Staff SRE)",
            password_hash=hash_password("ChangeMe123!"),
            role=Role.ENGINEER,
        )
        oncall = User(
            email="oncall@example.com",
            full_name="Jordan Lee (Primary On-Call)",
            password_hash=hash_password("ChangeMe123!"),
            role=Role.ON_CALL_ENGINEER,
        )
        viewer = User(
            email="viewer@example.com",
            full_name="Sam Taylor (Observer)",
            password_hash=hash_password("ChangeMe123!"),
            role=Role.VIEWER,
        )
        session.add_all([admin, engineer, oncall, viewer])
        await session.flush()

        print("Seeding services...")
        payment = Service(
            name="Payment Gateway API",
            slug="payment-api",
            description="Authorizes payment transactions, credit card tokens, refunds, and merchant settlement.",
            owner_id=engineer.id,
            repository="https://github.com/enterprise/payment-api",
            environment="production",
            health_endpoint="https://payment-api.internal/health",
            status=ServiceStatus.DEGRADED,
            criticality=Criticality.CRITICAL,
        )
        order_svc = Service(
            name="Order Processing Service",
            slug="order-service",
            description="State machine for customer checkouts, cart management, and order fulfillment pipelines.",
            owner_id=engineer.id,
            repository="https://github.com/enterprise/order-service",
            environment="production",
            health_endpoint="https://order-service.internal/health",
            status=ServiceStatus.HEALTHY,
            criticality=Criticality.HIGH,
        )
        user_svc = Service(
            name="Identity & User Service",
            slug="user-service",
            description="Authentication, OAuth2 sessions, and profile metadata management.",
            owner_id=oncall.id,
            repository="https://github.com/enterprise/user-service",
            environment="production",
            health_endpoint="https://user-service.internal/health",
            status=ServiceStatus.HEALTHY,
            criticality=Criticality.HIGH,
        )
        inventory_svc = Service(
            name="Inventory Catalog Service",
            slug="inventory-service",
            description="Real-time stock reservation, warehouse sync, and catalog availability lookups.",
            owner_id=engineer.id,
            repository="https://github.com/enterprise/inventory-service",
            environment="production",
            health_endpoint="https://inventory.internal/health",
            status=ServiceStatus.DEGRADED,
            criticality=Criticality.MEDIUM,
        )
        notification_svc = Service(
            name="Notification Service",
            slug="notification-service",
            description="Multi-channel messaging service dispatching SMS, push notifications, and customer emails.",
            owner_id=oncall.id,
            repository="https://github.com/enterprise/notification-service",
            environment="production",
            health_endpoint="https://notifications.internal/health",
            status=ServiceStatus.HEALTHY,
            criticality=Criticality.LOW,
        )
        session.add_all([payment, order_svc, user_svc, inventory_svc, notification_svc])
        await session.flush()

        print("Seeding health check telemetry...")
        for s in [payment, order_svc, user_svc, inventory_svc, notification_svc]:
            for i in range(12):
                chk_time = now - timedelta(minutes=(12 - i) * 5)
                is_deg = (s == payment and i >= 8) or (s == inventory_svc and i >= 9)
                session.add(
                    ServiceHealthCheck(
                        service_id=s.id,
                        http_status=503 if is_deg else 200,
                        response_time_ms=850 if is_deg else 42 + (i * 3),
                        availability=not is_deg,
                        error="HTTP 503: Upstream service overloaded" if is_deg else None,
                        created_at=chk_time,
                    )
                )

        print("Seeding incidents across full lifecycle...")
        # 1. Active Critical SEV1 Incident
        inc1_detected = now - timedelta(minutes=65)
        inc1_ack = inc1_detected + timedelta(minutes=4)
        inc1 = Incident(
            service_id=payment.id,
            title="Payment API elevated 5xx rate during card authorization",
            description="Elevated error rates on POST /v1/charges causing failed customer checkouts and retry storms.",
            status=IncidentStatus.INVESTIGATING,
            severity=IncidentSeverity.SEV1,
            detected_at=inc1_detected,
            acknowledged_at=inc1_ack,
            assignee_id=oncall.id,
            created_at=inc1_detected,
        )
        session.add(inc1)
        await session.flush()

        session.add_all(
            [
                TimelineEvent(
                    incident_id=inc1.id,
                    actor_id=None,
                    event_type="IncidentCreated",
                    message="Automated detection: Prometheus 5xx threshold violated (> 5%).",
                    metadata_json={"alert_source": "prometheus"},
                    created_at=inc1_detected,
                ),
                TimelineEvent(
                    incident_id=inc1.id,
                    actor_id=oncall.id,
                    event_type="IncidentAcknowledged",
                    message=f"Acknowledged by {oncall.full_name} via PagerDuty webhook.",
                    metadata_json={"mtta_minutes": 4.0},
                    created_at=inc1_ack,
                ),
                TimelineEvent(
                    incident_id=inc1.id,
                    actor_id=oncall.id,
                    event_type="IncidentAssigned",
                    message=f"Assigned to {oncall.full_name}.",
                    metadata_json={},
                    created_at=inc1_ack + timedelta(minutes=1),
                ),
                IncidentAssignment(
                    incident_id=inc1.id,
                    assignee_id=oncall.id,
                    assigned_by_id=None,
                    reason="Primary On-Call Rotation auto-assignment",
                    created_at=inc1_ack,
                ),
                IncidentComment(
                    incident_id=inc1.id,
                    author_id=oncall.id,
                    body="Investigating DB connection pool metrics. Postgres replica shows 98 active connections out of 100 limit.",
                    created_at=inc1_ack + timedelta(minutes=10),
                ),
            ]
        )

        # 2. SEV2 Incident - Inventory Cache Stampede (Mitigating)
        inc2_detected = now - timedelta(minutes=95)
        inc2_ack = inc2_detected + timedelta(minutes=8)
        inc2 = Incident(
            service_id=inventory_svc.id,
            title="Inventory Service Redis cache saturation and query latency spike",
            description="Cache miss stampede on flash-sale product IDs resulting in unindexed queries against database.",
            status=IncidentStatus.MITIGATING,
            severity=IncidentSeverity.SEV2,
            detected_at=inc2_detected,
            acknowledged_at=inc2_ack,
            assignee_id=engineer.id,
            created_at=inc2_detected,
        )
        session.add(inc2)
        await session.flush()

        session.add_all(
            [
                TimelineEvent(
                    incident_id=inc2.id,
                    actor_id=None,
                    event_type="IncidentCreated",
                    message="Incident triggered by Datadog APM p99 latency monitor (> 1200ms).",
                    metadata_json={"p99_latency_ms": 1450},
                    created_at=inc2_detected,
                ),
                TimelineEvent(
                    incident_id=inc2.id,
                    actor_id=engineer.id,
                    event_type="IncidentStatusChanged",
                    message="Moved to MITIGATING after enabling stale-while-revalidate cache fallback.",
                    metadata_json={"from": "INVESTIGATING", "to": "MITIGATING"},
                    created_at=inc2_detected + timedelta(minutes=40),
                ),
            ]
        )

        # 3. SEV3 Incident - Notification Dispatch Backlog (Triggered)
        inc3_detected = now - timedelta(minutes=18)
        inc3 = Incident(
            service_id=notification_svc.id,
            title="Notification Queue consumer lag exceeding SLA threshold",
            description="Celery worker queue for order confirmation emails delayed by 450 messages.",
            status=IncidentStatus.TRIGGERED,
            severity=IncidentSeverity.SEV3,
            detected_at=inc3_detected,
            created_at=inc3_detected,
        )
        session.add(inc3)
        await session.flush()

        # 4. Resolved Historical Incident 1 (Payment Auth Timeout - 2 days ago)
        h1_detected = now - timedelta(days=2, hours=4)
        h1_ack = h1_detected + timedelta(minutes=5)
        h1_resolved = h1_detected + timedelta(minutes=38)
        h1 = Incident(
            service_id=payment.id,
            title="Payment API connection pool exhaustion during flash sale",
            description="Database pool saturation caused 504 Gateway Timeouts on checkout endpoints.",
            status=IncidentStatus.CLOSED,
            severity=IncidentSeverity.SEV1,
            detected_at=h1_detected,
            acknowledged_at=h1_ack,
            resolved_at=h1_resolved,
            closed_at=h1_resolved + timedelta(hours=2),
            assignee_id=engineer.id,
            created_at=h1_detected,
        )
        session.add(h1)
        await session.flush()

        # 5. Resolved Historical Incident 2 (User Service token verification - 4 days ago)
        h2_detected = now - timedelta(days=4, hours=2)
        h2_ack = h2_detected + timedelta(minutes=3)
        h2_resolved = h2_detected + timedelta(minutes=24)
        h2 = Incident(
            service_id=user_svc.id,
            title="OAuth token verification latency spike",
            description="Redis auth cache eviction triggered cascading slow JWT validation queries.",
            status=IncidentStatus.RESOLVED,
            severity=IncidentSeverity.SEV2,
            detected_at=h2_detected,
            acknowledged_at=h2_ack,
            resolved_at=h2_resolved,
            closed_at=h2_resolved + timedelta(hours=1),
            assignee_id=oncall.id,
            created_at=h2_detected,
        )
        session.add(h2)
        await session.flush()

        # 6. Resolved Historical Incident 3 (Order Service idempotency deadlock - 6 days ago)
        h3_detected = now - timedelta(days=6, hours=1)
        h3_ack = h3_detected + timedelta(minutes=6)
        h3_resolved = h3_detected + timedelta(minutes=48)
        h3 = Incident(
            service_id=order_svc.id,
            title="Order creation row-lock contention under concurrent submission",
            description="Deadlock detected in PostgreSQL order_items table for bulk batch checkout.",
            status=IncidentStatus.CLOSED,
            severity=IncidentSeverity.SEV2,
            detected_at=h3_detected,
            acknowledged_at=h3_ack,
            resolved_at=h3_resolved,
            closed_at=h3_resolved + timedelta(hours=3),
            assignee_id=engineer.id,
            created_at=h3_detected,
        )
        session.add(h3)
        await session.flush()

        print("Seeding alerts & deduplication records...")
        session.add_all(
            [
                Alert(
                    service_id=payment.id,
                    incident_id=inc1.id,
                    source="prometheus",
                    severity=AlertSeverity.CRITICAL,
                    title="High 5xx HTTP Error Rate on /v1/charges",
                    description="Error rate > 8% for 5m evaluation period. P99 latency is 3400ms.",
                    fingerprint="payment-api-5xx-production",
                    metadata_json={
                        "metric": "http_requests_total",
                        "code": "500",
                        "cluster": "prod-us-east-1",
                    },
                    first_seen=inc1_detected,
                    last_seen=now - timedelta(minutes=2),
                    occurrence_count=14,
                    status=AlertStatus.OPEN,
                ),
                Alert(
                    service_id=payment.id,
                    incident_id=inc1.id,
                    source="datadog",
                    severity=AlertSeverity.CRITICAL,
                    title="PostgreSQL Primary Connection Pool Saturation",
                    description="Active database connections at 96% of pool capacity limit (96/100).",
                    fingerprint="payment-db-pool-saturation",
                    metadata_json={"active_conn": 96, "max_conn": 100},
                    first_seen=inc1_detected + timedelta(minutes=2),
                    last_seen=now - timedelta(minutes=5),
                    occurrence_count=8,
                    status=AlertStatus.OPEN,
                ),
                Alert(
                    service_id=inventory_svc.id,
                    incident_id=inc2.id,
                    source="datadog",
                    severity=AlertSeverity.ERROR,
                    title="Redis Cache Hit Ratio Dropped Below 60%",
                    description="Cache hit ratio dropped from 94% to 54% in 10 minutes.",
                    fingerprint="inventory-redis-cache-miss-storm",
                    metadata_json={"hit_ratio": 0.54, "keyspace": "inventory:stock"},
                    first_seen=inc2_detected,
                    last_seen=now - timedelta(minutes=15),
                    occurrence_count=5,
                    status=AlertStatus.ACKNOWLEDGED,
                ),
                Alert(
                    service_id=notification_svc.id,
                    incident_id=inc3.id,
                    source="cloudwatch",
                    severity=AlertSeverity.WARNING,
                    title="SQS ApproximateNumberOfMessagesVisible High",
                    description="Notification queue backlog exceeded 400 messages threshold.",
                    fingerprint="notification-sqs-backlog-warn",
                    metadata_json={"queue": "prod-notification-dispatch", "depth": 452},
                    first_seen=inc3_detected,
                    last_seen=now - timedelta(minutes=1),
                    occurrence_count=3,
                    status=AlertStatus.OPEN,
                ),
            ]
        )

        print("Seeding structured logs with secret redaction...")
        session.add_all(
            [
                LogEntry(
                    timestamp=now - timedelta(minutes=30),
                    service_id=payment.id,
                    service_name="payment-api",
                    level="ERROR",
                    message="Database connection pool timeout while attempting card tokenization. Pool exhausted.",
                    trace_id="trace-pay-9081",
                    request_id="req-21445",
                    metadata_json={"endpoint": "/v1/charges", "client_ip": "10.0.4.12"},
                ),
                LogEntry(
                    timestamp=now - timedelta(minutes=28),
                    service_id=payment.id,
                    service_name="payment-api",
                    level="CRITICAL",
                    message="Cannot acquire connection from pool: timeout after 3000ms. Aborting transaction.",
                    trace_id="trace-pay-9082",
                    request_id="req-21449",
                    metadata_json={"active_connections": 98, "queue_depth": 14},
                ),
                LogEntry(
                    timestamp=now - timedelta(minutes=25),
                    service_id=payment.id,
                    service_name="payment-api",
                    level="WARN",
                    message="Retrying downstream payment provider call with exponential backoff (attempt 2 of 3).",
                    trace_id="trace-pay-9085",
                    request_id="req-21455",
                    metadata_json={"provider": "stripe", "backoff_ms": 1200},
                ),
                LogEntry(
                    timestamp=now - timedelta(minutes=20),
                    service_id=inventory_svc.id,
                    service_name="inventory-service",
                    level="WARN",
                    message="Cache miss for SKU-884912; falling back to direct database query.",
                    trace_id="trace-inv-4011",
                    request_id="req-66512",
                    metadata_json={"sku": "SKU-884912", "cache_key": "stock:884912"},
                ),
                LogEntry(
                    timestamp=now - timedelta(minutes=10),
                    service_id=notification_svc.id,
                    service_name="notification-service",
                    level="INFO",
                    message="Worker dispatched 250 batch emails successfully to SES provider.",
                    trace_id="trace-notif-110",
                    request_id="req-8819",
                    metadata_json={"provider": "ses", "batch_size": 250},
                ),
            ]
        )

        print("Seeding operational runbooks...")
        session.add_all(
            [
                Runbook(
                    service_id=payment.id,
                    title="Payment API Database Pool Exhaustion Runbook",
                    incident_type="database-pool-exhaustion",
                    body=(
                        "### Triage & Remediation Steps\n\n"
                        "1. **Check Active Database Sessions**:\n"
                        "   Run query `SELECT count(*), state FROM pg_stat_activity WHERE datname='payments' GROUP BY state;`\n\n"
                        "2. **Identify Long-Running or Leaked Transactions**:\n"
                        "   Inspect `pg_stat_activity` for queries with duration > 10s.\n\n"
                        "3. **Enable Temporary Connection Throttling**:\n"
                        "   Tune ingress gateway rate-limiting to reduce concurrency spike.\n\n"
                        "4. **Failover or Scale Pool**:\n"
                        "   Authorize increase in PgBouncer pool ceiling from 100 to 150 if host memory utilization is under 60%.\n\n"
                        "5. **Escalation**:\n"
                        "   Page Database Reliability On-Call if lock contention does not clear within 10 minutes."
                    ),
                    owner_id=engineer.id,
                ),
                Runbook(
                    service_id=inventory_svc.id,
                    title="Redis Cache Stampede & Degraded Query Runbook",
                    incident_type="cache-stampede",
                    body=(
                        "### Triage & Remediation Steps\n\n"
                        "1. **Inspect Redis Memory and Eviction Rate**:\n"
                        "   Execute `INFO memory` and `INFO stats` on primary Redis cluster.\n\n"
                        "2. **Pre-warm High Velocity Keys**:\n"
                        "   Run inventory prewarm script for active promotional items.\n\n"
                        "3. **Enable Stale-While-Revalidate Fallback**:\n"
                        "   Flip feature flag `inventory.cache.swr_enabled=true`.\n\n"
                        "4. **Verify Database Replica Latency**:\n"
                        "   Ensure read replicas are not lagging primary by > 5 seconds."
                    ),
                    owner_id=engineer.id,
                ),
                Runbook(
                    service_id=order_svc.id,
                    title="Order Processing Deadlock Resolution",
                    incident_type="database-deadlock",
                    body=(
                        "### Triage & Remediation Steps\n\n"
                        "1. **Inspect Deadlock Telemetry in Postgres Logs**:\n"
                        "   Search for `deadlock detected` in cloudwatch/postgres logs to find conflicting SQL statements.\n\n"
                        "2. **Verify Row Locking Ordering**:\n"
                        "   Ensure order item insertion locks rows in consistent primary key order.\n\n"
                        "3. **Enable Jittered Retries**:\n"
                        "   Confirm application handles serialization failures with exponential backoff."
                    ),
                    owner_id=engineer.id,
                ),
            ]
        )

        print("Seeding AI analysis for primary incident...")
        session.add(
            AIAnalysis(
                incident_id=inc1.id,
                provider="heuristic-contextual",
                summary=(
                    "AIOps Incident Synthesis for Payment Gateway API: Telemetry demonstrates an acute connection pool "
                    "saturation event triggering cascading HTTP 5xx responses. Correlated 2 high-severity alerts from Prometheus and Datadog."
                ),
                probable_causes=[
                    "HYPOTHESIS 1: Database connection pool saturation on Payment API primary cluster (96/100 active connections).",
                    "HYPOTHESIS 2: Upstream gateway request thread starvation caused by 3400ms P99 database query timeout.",
                ],
                evidence=[
                    {
                        "kind": "alert",
                        "fact": "Prometheus HTTP 5xx rate exceeded 8% threshold on /v1/charges",
                        "source": "prometheus",
                    },
                    {
                        "kind": "alert",
                        "fact": "Datadog connection pool capacity reached 96%",
                        "source": "datadog",
                    },
                    {
                        "kind": "log",
                        "fact": "Database connection pool timeout while attempting card tokenization",
                        "source": "trace-pay-9081",
                    },
                    {
                        "kind": "runbook",
                        "fact": "Found matching runbook: Payment API Database Pool Exhaustion Runbook",
                        "source": "runbook:payment-api",
                    },
                ],
                recommended_actions=[
                    "1. Run pg_stat_activity to inspect queries holding locks on payment ledger tables.",
                    "2. Temporarily throttle non-essential background reconciliation jobs.",
                    "3. Apply PgBouncer pool ceiling expansion from 100 to 150.",
                    "4. Escalate to database owner if latency remains above 1000ms.",
                ],
                confidence=0.88,
                related_incidents=[
                    f"Payment API connection pool exhaustion during flash sale (ID: {h1.id})",
                ],
            )
        )

        print("Seeding postmortem for historical incident...")
        session.add(
            Postmortem(
                incident_id=h1.id,
                summary="Payment API experienced 38 minutes of elevated 504 errors during flash checkout event.",
                impact="Approximately 4.2% of checkout attempts failed or required user retry. Estimated $18,400 delayed gross merchandise value.",
                timeline="14:02 UTC - First alert fired\n14:07 UTC - On-call acknowledged\n14:22 UTC - Pool expansion applied\n14:40 UTC - Error rate normalized",
                root_cause="Database connection pool ceiling of 100 connections was inadequate for a 3x traffic surge during promotional sale.",
                contributing_factors="Canary environment tests did not simulate concurrent database connection saturation.",
                resolution="Increased connection pool capacity to 200 via PgBouncer and implemented client-side retry circuit breakers.",
                preventive_actions="1. Configure automated pool saturation alerts at 80% threshold.\n2. Conduct synthetic load test before next major marketing event.",
                lessons_learned="Connection limits must scale automatically with compute capacity.",
                owner_id=engineer.id,
                status="APPROVED",
            )
        )

        await session.commit()
        print(
            "Seed completed successfully! All services, incidents, alerts, telemetry, runbooks, and users ready."
        )


if __name__ == "__main__":
    asyncio.run(seed())
