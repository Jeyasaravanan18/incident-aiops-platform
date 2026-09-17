import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.database import get_database
from app.core.security import hash_password
from app.models.enums import (
    AlertSeverity,
    AlertStatus,
    Criticality,
    IncidentSeverity,
    IncidentStatus,
    Role,
    ServiceStatus,
)


async def seed() -> None:
    db = get_database()
    print(f"Connecting to MongoDB Atlas database '{db.name}'...")

    # Check if already seeded
    existing = await db.users.find_one({"email": "admin@example.com"})
    if existing is not None:
        print("Database already seeded. Cleaning collections for fresh scenario...")
        for col in [
            "ai_analyses",
            "postmortems",
            "timeline_events",
            "incident_comments",
            "incident_assignments",
            "alerts",
            "incidents",
            "logs",
            "health_checks",
            "runbooks",
            "services",
            "notifications",
            "idempotency_records",
            "refresh_tokens",
            "users",
        ]:
            await db[col].delete_many({})

    now = datetime.now(UTC)

    # 1. Users
    print("Seeding users...")
    admin_id = str(uuid4())
    engineer_id = str(uuid4())
    oncall_id = str(uuid4())
    viewer_id = str(uuid4())

    users = [
        {
            "id": admin_id,
            "email": "admin@example.com",
            "full_name": "Avery Morgan (Admin)",
            "password_hash": hash_password("ChangeMe123!"),
            "role": Role.ADMIN.value,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": engineer_id,
            "email": "engineer@example.com",
            "full_name": "Riya Shah (Staff SRE)",
            "password_hash": hash_password("ChangeMe123!"),
            "role": Role.ENGINEER.value,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": oncall_id,
            "email": "oncall@example.com",
            "full_name": "Jordan Lee (Primary On-Call)",
            "password_hash": hash_password("ChangeMe123!"),
            "role": Role.ON_CALL_ENGINEER.value,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": viewer_id,
            "email": "viewer@example.com",
            "full_name": "Sam Taylor (Observer)",
            "password_hash": hash_password("ChangeMe123!"),
            "role": Role.VIEWER.value,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
    ]
    await db.users.insert_many(users)

    # 2. Services
    print("Seeding services...")
    payment_id = str(uuid4())
    order_id = str(uuid4())
    user_svc_id = str(uuid4())
    inventory_id = str(uuid4())
    notification_id = str(uuid4())

    services = [
        {
            "id": payment_id,
            "name": "Payment Gateway API",
            "slug": "payment-api",
            "description": "Authorizes payment transactions, credit card tokens, refunds, and merchant settlement.",
            "owner_id": engineer_id,
            "repository": "https://github.com/enterprise/payment-api",
            "environment": "production",
            "health_endpoint": "https://payment-api.internal/health",
            "status": ServiceStatus.DEGRADED.value,
            "criticality": Criticality.CRITICAL.value,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": order_id,
            "name": "Order Processing Service",
            "slug": "order-service",
            "description": "State machine for customer checkouts, cart management, and order fulfillment pipelines.",
            "owner_id": engineer_id,
            "repository": "https://github.com/enterprise/order-service",
            "environment": "production",
            "health_endpoint": "https://order-service.internal/health",
            "status": ServiceStatus.HEALTHY.value,
            "criticality": Criticality.HIGH.value,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": user_svc_id,
            "name": "Identity & User Service",
            "slug": "user-service",
            "description": "Authentication, OAuth2 sessions, and profile metadata management.",
            "owner_id": oncall_id,
            "repository": "https://github.com/enterprise/user-service",
            "environment": "production",
            "health_endpoint": "https://user-service.internal/health",
            "status": ServiceStatus.HEALTHY.value,
            "criticality": Criticality.HIGH.value,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": inventory_id,
            "name": "Inventory Catalog Service",
            "slug": "inventory-service",
            "description": "Real-time stock reservation, warehouse sync, and catalog availability lookups.",
            "owner_id": engineer_id,
            "repository": "https://github.com/enterprise/inventory-service",
            "environment": "production",
            "health_endpoint": "https://inventory.internal/health",
            "status": ServiceStatus.DEGRADED.value,
            "criticality": Criticality.MEDIUM.value,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": notification_id,
            "name": "Notification Service",
            "slug": "notification-service",
            "description": "Multi-channel messaging service dispatching SMS, push notifications, and customer emails.",
            "owner_id": oncall_id,
            "repository": "https://github.com/enterprise/notification-service",
            "environment": "production",
            "health_endpoint": "https://notifications.internal/health",
            "status": ServiceStatus.HEALTHY.value,
            "criticality": Criticality.LOW.value,
            "created_at": now,
            "updated_at": now,
        },
    ]
    await db.services.insert_many(services)

    # 3. Health Checks
    print("Seeding health check telemetry...")
    health_checks = []
    for sid, s_slug in [
        (payment_id, "payment-api"),
        (order_id, "order-service"),
        (user_svc_id, "user-service"),
        (inventory_id, "inventory-service"),
        (notification_id, "notification-service"),
    ]:
        for i in range(12):
            chk_time = now - timedelta(minutes=(12 - i) * 5)
            is_deg = (s_slug == "payment-api" and i >= 8) or (
                s_slug == "inventory-service" and i >= 9
            )
            health_checks.append(
                {
                    "id": str(uuid4()),
                    "service_id": sid,
                    "http_status": 503 if is_deg else 200,
                    "response_time_ms": 850 if is_deg else 42 + (i * 3),
                    "availability": not is_deg,
                    "error": "HTTP 503: Upstream service overloaded" if is_deg else None,
                    "created_at": chk_time,
                }
            )
    await db.health_checks.insert_many(health_checks)

    # 4. Incidents across full lifecycle
    print("Seeding incidents across full lifecycle...")
    inc1_id = str(uuid4())
    inc1_det = now - timedelta(minutes=65)
    inc1_ack = inc1_det + timedelta(minutes=4)

    inc2_id = str(uuid4())
    inc2_det = now - timedelta(minutes=95)
    inc2_ack = inc2_det + timedelta(minutes=8)

    inc3_id = str(uuid4())
    inc3_det = now - timedelta(minutes=18)

    h1_id = str(uuid4())
    h1_det = now - timedelta(days=2, hours=4)
    h1_ack = h1_det + timedelta(minutes=5)
    h1_res = h1_det + timedelta(minutes=38)

    h2_id = str(uuid4())
    h2_det = now - timedelta(days=4, hours=2)
    h2_ack = h2_det + timedelta(minutes=3)
    h2_res = h2_det + timedelta(minutes=24)

    h3_id = str(uuid4())
    h3_det = now - timedelta(days=6, hours=1)
    h3_ack = h3_det + timedelta(minutes=6)
    h3_res = h3_det + timedelta(minutes=48)

    incidents = [
        {
            "id": inc1_id,
            "service_id": payment_id,
            "title": "Payment API elevated 5xx rate during card authorization",
            "description": "Elevated error rates on POST /v1/charges causing failed customer checkouts and retry storms.",
            "status": IncidentStatus.INVESTIGATING.value,
            "severity": IncidentSeverity.SEV1.value,
            "detected_at": inc1_det,
            "acknowledged_at": inc1_ack,
            "resolved_at": None,
            "closed_at": None,
            "assignee_id": oncall_id,
            "created_at": inc1_det,
            "updated_at": now,
        },
        {
            "id": inc2_id,
            "service_id": inventory_id,
            "title": "Inventory Service Redis cache saturation and query latency spike",
            "description": "Cache miss stampede on flash-sale product IDs resulting in unindexed queries against database.",
            "status": IncidentStatus.MITIGATING.value,
            "severity": IncidentSeverity.SEV2.value,
            "detected_at": inc2_det,
            "acknowledged_at": inc2_ack,
            "resolved_at": None,
            "closed_at": None,
            "assignee_id": engineer_id,
            "created_at": inc2_det,
            "updated_at": now,
        },
        {
            "id": inc3_id,
            "service_id": notification_id,
            "title": "Notification Queue consumer lag exceeding SLA threshold",
            "description": "Celery worker queue for order confirmation emails delayed by 450 messages.",
            "status": IncidentStatus.TRIGGERED.value,
            "severity": IncidentSeverity.SEV3.value,
            "detected_at": inc3_det,
            "acknowledged_at": None,
            "resolved_at": None,
            "closed_at": None,
            "assignee_id": None,
            "created_at": inc3_det,
            "updated_at": now,
        },
        {
            "id": h1_id,
            "service_id": payment_id,
            "title": "Payment API connection pool exhaustion during flash sale",
            "description": "Database pool saturation caused 504 Gateway Timeouts on checkout endpoints.",
            "status": IncidentStatus.CLOSED.value,
            "severity": IncidentSeverity.SEV1.value,
            "detected_at": h1_det,
            "acknowledged_at": h1_ack,
            "resolved_at": h1_res,
            "closed_at": h1_res + timedelta(hours=2),
            "assignee_id": engineer_id,
            "created_at": h1_det,
            "updated_at": h1_res + timedelta(hours=2),
        },
        {
            "id": h2_id,
            "service_id": user_svc_id,
            "title": "OAuth token verification latency spike",
            "description": "Redis auth cache eviction triggered cascading slow JWT validation queries.",
            "status": IncidentStatus.RESOLVED.value,
            "severity": IncidentSeverity.SEV2.value,
            "detected_at": h2_det,
            "acknowledged_at": h2_ack,
            "resolved_at": h2_res,
            "closed_at": h2_res + timedelta(hours=1),
            "assignee_id": oncall_id,
            "created_at": h2_det,
            "updated_at": h2_res,
        },
        {
            "id": h3_id,
            "service_id": order_id,
            "title": "Order creation row-lock contention under concurrent submission",
            "description": "Deadlock detected in order_items table for bulk batch checkout.",
            "status": IncidentStatus.CLOSED.value,
            "severity": IncidentSeverity.SEV2.value,
            "detected_at": h3_det,
            "acknowledged_at": h3_ack,
            "resolved_at": h3_res,
            "closed_at": h3_res + timedelta(hours=3),
            "assignee_id": engineer_id,
            "created_at": h3_det,
            "updated_at": h3_res + timedelta(hours=3),
        },
    ]
    await db.incidents.insert_many(incidents)

    # 5. Timeline Events & Comments
    timeline_events = [
        {
            "id": str(uuid4()),
            "incident_id": inc1_id,
            "actor_id": None,
            "event_type": "IncidentCreated",
            "message": "Automated detection: Prometheus 5xx threshold violated (> 5%).",
            "metadata_json": {"alert_source": "prometheus"},
            "created_at": inc1_det,
        },
        {
            "id": str(uuid4()),
            "incident_id": inc1_id,
            "actor_id": oncall_id,
            "event_type": "IncidentAcknowledged",
            "message": "Acknowledged by Jordan Lee via PagerDuty webhook.",
            "metadata_json": {"mtta_minutes": 4.0},
            "created_at": inc1_ack,
        },
        {
            "id": str(uuid4()),
            "incident_id": inc1_id,
            "actor_id": oncall_id,
            "event_type": "IncidentAssigned",
            "message": "Assigned to Jordan Lee (Primary On-Call).",
            "metadata_json": {},
            "created_at": inc1_ack + timedelta(minutes=1),
        },
        {
            "id": str(uuid4()),
            "incident_id": inc2_id,
            "actor_id": None,
            "event_type": "IncidentCreated",
            "message": "Incident triggered by Datadog APM p99 latency monitor (> 1200ms).",
            "metadata_json": {"p99_latency_ms": 1450},
            "created_at": inc2_det,
        },
        {
            "id": str(uuid4()),
            "incident_id": inc2_id,
            "actor_id": engineer_id,
            "event_type": "IncidentStatusChanged",
            "message": "Moved to MITIGATING after enabling stale-while-revalidate cache fallback.",
            "metadata_json": {"from": "INVESTIGATING", "to": "MITIGATING"},
            "created_at": inc2_det + timedelta(minutes=40),
        },
    ]
    await db.timeline_events.insert_many(timeline_events)

    comments = [
        {
            "id": str(uuid4()),
            "incident_id": inc1_id,
            "author_id": oncall_id,
            "body": "Investigating DB connection pool metrics. Postgres replica shows 98 active connections out of 100 limit.",
            "created_at": inc1_ack + timedelta(minutes=10),
            "edited_at": None,
        }
    ]
    await db.incident_comments.insert_many(comments)

    # 6. Alerts
    print("Seeding alerts & deduplication records...")
    alerts = [
        {
            "id": str(uuid4()),
            "service_id": payment_id,
            "incident_id": inc1_id,
            "source": "prometheus",
            "severity": AlertSeverity.CRITICAL.value,
            "title": "High 5xx HTTP Error Rate on /v1/charges",
            "description": "Error rate > 8% for 5m evaluation period. P99 latency is 3400ms.",
            "fingerprint": "payment-api-5xx-production",
            "metadata_json": {
                "metric": "http_requests_total",
                "code": "500",
                "cluster": "prod-us-east-1",
            },
            "first_seen": inc1_det,
            "last_seen": now - timedelta(minutes=2),
            "occurrence_count": 14,
            "status": AlertStatus.OPEN.value,
            "created_at": inc1_det,
        },
        {
            "id": str(uuid4()),
            "service_id": payment_id,
            "incident_id": inc1_id,
            "source": "datadog",
            "severity": AlertSeverity.CRITICAL.value,
            "title": "PostgreSQL Primary Connection Pool Saturation",
            "description": "Active database connections at 96% of pool capacity limit (96/100).",
            "fingerprint": "payment-db-pool-saturation",
            "metadata_json": {"active_conn": 96, "max_conn": 100},
            "first_seen": inc1_det + timedelta(minutes=2),
            "last_seen": now - timedelta(minutes=5),
            "occurrence_count": 8,
            "status": AlertStatus.OPEN.value,
            "created_at": inc1_det + timedelta(minutes=2),
        },
        {
            "id": str(uuid4()),
            "service_id": inventory_id,
            "incident_id": inc2_id,
            "source": "datadog",
            "severity": AlertSeverity.ERROR.value,
            "title": "Redis Cache Hit Ratio Dropped Below 60%",
            "description": "Cache hit ratio dropped from 94% to 54% in 10 minutes.",
            "fingerprint": "inventory-redis-cache-miss-storm",
            "metadata_json": {"hit_ratio": 0.54, "keyspace": "inventory:stock"},
            "first_seen": inc2_det,
            "last_seen": now - timedelta(minutes=15),
            "occurrence_count": 5,
            "status": AlertStatus.ACKNOWLEDGED.value,
            "created_at": inc2_det,
        },
        {
            "id": str(uuid4()),
            "service_id": notification_id,
            "incident_id": inc3_id,
            "source": "cloudwatch",
            "severity": AlertSeverity.WARNING.value,
            "title": "SQS ApproximateNumberOfMessagesVisible High",
            "description": "Notification queue backlog exceeded 400 messages threshold.",
            "fingerprint": "notification-sqs-backlog-warn",
            "metadata_json": {"queue": "prod-notification-dispatch", "depth": 452},
            "first_seen": inc3_det,
            "last_seen": now - timedelta(minutes=1),
            "occurrence_count": 3,
            "status": AlertStatus.OPEN.value,
            "created_at": inc3_det,
        },
    ]
    await db.alerts.insert_many(alerts)

    # 7. Logs
    print("Seeding logs...")
    logs = [
        {
            "id": str(uuid4()),
            "timestamp": now - timedelta(minutes=30),
            "service_id": payment_id,
            "service_name": "payment-api",
            "level": "ERROR",
            "message": "Database connection pool timeout while attempting card tokenization. Pool exhausted.",
            "trace_id": "trace-pay-9081",
            "request_id": "req-21445",
            "metadata_json": {"endpoint": "/v1/charges", "client_ip": "10.0.4.12"},
        },
        {
            "id": str(uuid4()),
            "timestamp": now - timedelta(minutes=28),
            "service_id": payment_id,
            "service_name": "payment-api",
            "level": "CRITICAL",
            "message": "Cannot acquire connection from pool: timeout after 3000ms. Aborting transaction.",
            "trace_id": "trace-pay-9082",
            "request_id": "req-21449",
            "metadata_json": {"active_connections": 98, "queue_depth": 14},
        },
        {
            "id": str(uuid4()),
            "timestamp": now - timedelta(minutes=25),
            "service_id": payment_id,
            "service_name": "payment-api",
            "level": "WARN",
            "message": "Retrying downstream payment provider call with exponential backoff (attempt 2 of 3).",
            "trace_id": "trace-pay-9085",
            "request_id": "req-21455",
            "metadata_json": {"provider": "stripe", "backoff_ms": 1200},
        },
        {
            "id": str(uuid4()),
            "timestamp": now - timedelta(minutes=20),
            "service_id": inventory_id,
            "service_name": "inventory-service",
            "level": "WARN",
            "message": "Cache miss for SKU-884912; falling back to direct database query.",
            "trace_id": "trace-inv-4011",
            "request_id": "req-66512",
            "metadata_json": {"sku": "SKU-884912", "cache_key": "stock:884912"},
        },
        {
            "id": str(uuid4()),
            "timestamp": now - timedelta(minutes=10),
            "service_id": notification_id,
            "service_name": "notification-service",
            "level": "INFO",
            "message": "Worker dispatched 250 batch emails successfully to SES provider.",
            "trace_id": "trace-notif-110",
            "request_id": "req-8819",
            "metadata_json": {"provider": "ses", "batch_size": 250},
        },
    ]
    await db.logs.insert_many(logs)

    # 8. Runbooks
    print("Seeding runbooks...")
    runbooks = [
        {
            "id": str(uuid4()),
            "service_id": payment_id,
            "title": "Payment API Database Pool Exhaustion Runbook",
            "incident_type": "database-pool-exhaustion",
            "body": (
                "### Triage & Remediation Steps\n\n"
                "1. **Check Active Database Sessions**:\n"
                "   Run query `SELECT count(*), state FROM pg_stat_activity WHERE datname='payments' GROUP BY state;`\n\n"
                "2. **Identify Long-Running or Leaked Transactions**:\n"
                "   Inspect `pg_stat_activity` for queries with duration > 10s.\n\n"
                "3. **Enable Temporary Connection Throttling**:\n"
                "   Tune ingress gateway rate-limiting to reduce concurrency spike.\n\n"
                "4. **Failover or Scale Pool**:\n"
                "   Authorize increase in PgBouncer pool ceiling from 100 to 150.\n\n"
                "5. **Escalation**:\n"
                "   Page Database Reliability On-Call if lock contention does not clear within 10 minutes."
            ),
            "owner_id": engineer_id,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": str(uuid4()),
            "service_id": inventory_id,
            "title": "Redis Cache Stampede & Degraded Query Runbook",
            "incident_type": "cache-stampede",
            "body": (
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
            "owner_id": engineer_id,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": str(uuid4()),
            "service_id": order_id,
            "title": "Order Processing Deadlock Resolution",
            "incident_type": "database-deadlock",
            "body": (
                "### Triage & Remediation Steps\n\n"
                "1. **Inspect Deadlock Telemetry**:\n"
                "   Search for `deadlock detected` in application logs to find conflicting SQL statements.\n\n"
                "2. **Verify Row Locking Ordering**:\n"
                "   Ensure order item insertion locks rows in consistent primary key order.\n\n"
                "3. **Enable Jittered Retries**:\n"
                "   Confirm application handles serialization failures with exponential backoff."
            ),
            "owner_id": engineer_id,
            "created_at": now,
            "updated_at": now,
        },
    ]
    await db.runbooks.insert_many(runbooks)

    # 9. AI Analysis
    print("Seeding AI analysis...")
    ai_analysis = {
        "id": str(uuid4()),
        "incident_id": inc1_id,
        "provider": "heuristic-contextual",
        "summary": (
            "AIOps Incident Synthesis for Payment Gateway API: Telemetry demonstrates an acute connection pool "
            "saturation event triggering cascading HTTP 5xx responses. Correlated 2 high-severity alerts from Prometheus and Datadog."
        ),
        "probable_causes": [
            "HYPOTHESIS 1: Database connection pool saturation on Payment API primary cluster (96/100 active connections).",
            "HYPOTHESIS 2: Upstream gateway request thread starvation caused by 3400ms P99 database query timeout.",
        ],
        "evidence": [
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
        "recommended_actions": [
            "1. Run pg_stat_activity to inspect queries holding locks on payment ledger tables.",
            "2. Temporarily throttle non-essential background reconciliation jobs.",
            "3. Apply PgBouncer pool ceiling expansion from 100 to 150.",
            "4. Escalate to database owner if latency remains above 1000ms.",
        ],
        "confidence": 0.88,
        "related_incidents": [
            f"Payment API connection pool exhaustion during flash sale (ID: {h1_id})",
        ],
        "created_at": now,
    }
    await db.ai_analyses.insert_one(ai_analysis)

    # 10. Postmortem
    print("Seeding postmortem...")
    postmortem = {
        "id": str(uuid4()),
        "incident_id": h1_id,
        "summary": "Payment API experienced 38 minutes of elevated 504 errors during flash checkout event.",
        "impact": "Approximately 4.2% of checkout attempts failed or required user retry. Estimated $18,400 delayed gross merchandise value.",
        "timeline": "14:02 UTC - First alert fired\n14:07 UTC - On-call acknowledged\n14:22 UTC - Pool expansion applied\n14:40 UTC - Error rate normalized",
        "root_cause": "Database connection pool ceiling of 100 connections was inadequate for a 3x traffic surge during promotional sale.",
        "contributing_factors": "Canary environment tests did not simulate concurrent database connection saturation.",
        "resolution": "Increased connection pool capacity to 200 and implemented client-side retry circuit breakers.",
        "preventive_actions": "1. Configure automated pool saturation alerts at 80% threshold.\n2. Conduct synthetic load test before next major marketing event.",
        "lessons_learned": "Connection limits must scale automatically with compute capacity.",
        "owner_id": engineer_id,
        "status": "APPROVED",
        "created_at": h1_res,
        "updated_at": h1_res,
    }
    await db.postmortems.insert_one(postmortem)

    print(
        "Seed completed successfully! MongoDB Atlas populated with all services, incidents, alerts, telemetry, runbooks, and users."
    )


if __name__ == "__main__":
    asyncio.run(seed())
