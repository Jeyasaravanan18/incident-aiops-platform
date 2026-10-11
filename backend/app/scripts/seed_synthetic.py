"""High-volume synthetic data generator for stress-testing and SQL analytics benchmarks.

Generates 2,000 synthetic incidents and 100,000 synthetic log entries across services.
All records are explicitly marked '[SYNTHETIC]' to ensure clear auditability.
"""

import asyncio
import random
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, insert, select

from app.core.database import AsyncSessionLocal
from app.models.enums import Criticality, IncidentSeverity, IncidentStatus, ServiceStatus
from app.models.incident import Incident
from app.models.log import LogEntry
from app.models.service import Service

LOG_LEVELS = ["INFO", "INFO", "INFO", "WARN", "ERROR", "CRITICAL"]
LOG_TEMPLATES = [
    "[SYNTHETIC] HTTP request processed in {latency}ms for path /v1/resource/{id}",
    "[SYNTHETIC] Database query execution time {latency}ms on cluster primary",
    "[SYNTHETIC] Connection pool acquired socket after {latency}ms wait",
    "[SYNTHETIC] Redis cache lookup hit for key session:{id}",
    "[SYNTHETIC] Redis cache miss for key metadata:{id}; fetching from storage",
    "[SYNTHETIC] Upstream gateway timeout after {latency}ms waiting for response",
    "[SYNTHETIC] Internal server exception: ConnectionResetError in worker thread {id}",
    "[SYNTHETIC] Garbage collection pause took {latency}ms, reclaimed 142MB heap",
    "[SYNTHETIC] Rate limiter token bucket consumed for client {id}",
    "[SYNTHETIC] Background task queue processed message batch with size {id}",
]

INCIDENT_TITLES = [
    "[SYNTHETIC] Elevated 5xx error rate on payment authorization endpoint",
    "[SYNTHETIC] High latency on customer checkout API gateway",
    "[SYNTHETIC] Database replica lag exceeding 15s replication window",
    "[SYNTHETIC] Connection pool exhaustion in auth microservice",
    "[SYNTHETIC] Redis cluster memory usage crossed 85% threshold",
    "[SYNTHETIC] SQS dead letter queue accumulation on fulfillment worker",
    "[SYNTHETIC] CPU throttling on kubernetes node pool pod autoscaler",
    "[SYNTHETIC] DNS resolution timeout when communicating with third-party gateway",
    "[SYNTHETIC] Disk I/O saturation on primary transaction database volume",
    "[SYNTHETIC] TLS handshake failure spike following certificate rotation",
]


async def seed_synthetic(target_incidents: int = 2000, target_logs: int = 100000) -> None:
    print(f"Starting synthetic generation: {target_incidents:,} incidents, {target_logs:,} logs...")
    start_time = time.perf_counter()

    async with AsyncSessionLocal() as session:
        # 1. Fetch or create test services
        services = list(await session.scalars(select(Service)))
        if not services:
            print("No existing services found. Creating 5 synthetic services...")
            for i in range(5):
                svc = Service(
                    id=uuid4(),
                    name=f"[SYNTHETIC] Service {i + 1}",
                    slug=f"synthetic-service-{i + 1}",
                    description=f"[SYNTHETIC] High-throughput benchmarking microservice {i + 1}",
                    environment="benchmark",
                    status=ServiceStatus.HEALTHY,
                    criticality=random.choice(list(Criticality)),
                )
                session.add(svc)
            await session.commit()
            services = list(await session.scalars(select(Service)))

        service_ids = [s.id for s in services]
        service_names = {s.id: s.name for s in services}

        # Clean existing synthetic data
        print("Cleaning prior [SYNTHETIC] benchmark records...")
        await session.execute(delete(LogEntry).where(LogEntry.message.like("[SYNTHETIC]%")))
        await session.execute(delete(Incident).where(Incident.title.like("[SYNTHETIC]%")))
        await session.commit()

        # 2. Bulk insert 2,000 synthetic incidents
        print(f"Inserting {target_incidents:,} synthetic incidents...")
        now = datetime.now(UTC)
        incident_rows = []

        statuses = [
            IncidentStatus.RESOLVED,
            IncidentStatus.CLOSED,
            IncidentStatus.INVESTIGATING,
            IncidentStatus.MITIGATING,
            IncidentStatus.ACKNOWLEDGED,
            IncidentStatus.TRIGGERED,
        ]

        for i in range(target_incidents):
            svc_id = random.choice(service_ids)
            # Spread across last 90 days
            created_offset = timedelta(
                days=random.randint(0, 89),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            created_at = now - created_offset
            detected_at = created_at

            status = random.choice(statuses)
            severity = random.choice(list(IncidentSeverity))

            ack_at = None
            res_at = None
            closed_at = None

            if status in (
                IncidentStatus.ACKNOWLEDGED,
                IncidentStatus.INVESTIGATING,
                IncidentStatus.MITIGATING,
                IncidentStatus.RESOLVED,
                IncidentStatus.CLOSED,
            ):
                ack_at = created_at + timedelta(minutes=random.randint(2, 25))

            if status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
                res_at = (ack_at or created_at) + timedelta(minutes=random.randint(15, 240))

            if status == IncidentStatus.CLOSED and res_at:
                closed_at = res_at + timedelta(hours=random.randint(1, 48))

            title = f"{random.choice(INCIDENT_TITLES)} #{i + 1}"
            desc = f"[SYNTHETIC] Automated stress benchmark incident #{i + 1} for {service_names[svc_id]}"

            incident_rows.append(
                {
                    "id": uuid4(),
                    "service_id": svc_id,
                    "title": title,
                    "description": desc,
                    "status": status,
                    "severity": severity,
                    "detected_at": detected_at,
                    "acknowledged_at": ack_at,
                    "resolved_at": res_at,
                    "closed_at": closed_at,
                    "created_at": created_at,
                    "updated_at": res_at or ack_at or created_at,
                }
            )

            if len(incident_rows) >= 500:
                await session.execute(insert(Incident), incident_rows)
                await session.commit()
                incident_rows = []

        if incident_rows:
            await session.execute(insert(Incident), incident_rows)
            await session.commit()

        # 3. Bulk insert 100,000 synthetic log entries in batches of 5,000
        print(f"Inserting {target_logs:,} synthetic log entries in batches of 5,000...")
        log_rows = []
        batch_size = 5000

        for i in range(target_logs):
            svc_id = random.choice(service_ids)
            svc_name = service_names[svc_id]
            log_time = now - timedelta(
                days=random.randint(0, 30),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
                seconds=random.randint(0, 59),
            )
            template = random.choice(LOG_TEMPLATES)
            msg = template.format(
                latency=random.randint(5, 2500),
                id=random.randint(1000, 99999),
            )

            log_rows.append(
                {
                    "id": uuid4(),
                    "service_id": svc_id,
                    "service_name": svc_name,
                    "timestamp": log_time,
                    "level": random.choice(LOG_LEVELS),
                    "message": msg,
                    "trace_id": f"trace-syn-{random.randint(100000, 999999)}",
                    "request_id": f"req-syn-{random.randint(100000, 999999)}",
                    "metadata_json": {
                        "environment": "benchmark",
                        "synthetic": True,
                        "batch_idx": i // batch_size,
                    },
                    "created_at": log_time,
                    "updated_at": log_time,
                }
            )

            if len(log_rows) >= batch_size:
                await session.execute(insert(LogEntry), log_rows)
                await session.commit()
                print(f"  Inserted {i + 1:,} / {target_logs:,} logs...")
                log_rows = []

        if log_rows:
            await session.execute(insert(LogEntry), log_rows)
            await session.commit()

    duration = time.perf_counter() - start_time
    print(f"Synthetic generation completed in {duration:.2f} seconds!")
    print(
        f"Summary: {target_incidents:,} synthetic incidents and {target_logs:,} synthetic logs created."
    )


if __name__ == "__main__":
    asyncio.run(seed_synthetic())
