# Production Incident Management & AIOps Platform - Technical Demo Script

This document provides a step-by-step script for demonstrating the platform to a **Senior Backend / SRE Interviewer**. It walks through the end-to-end incident lifecycle: alert ingestion, deduplication, deterministic severity escalation, real-time WebSocket event dissemination, AI/RAG context retrieval, collaborative command center triage, and blameless postmortem generation.

---

## 1. Pre-Flight Setup & Seeding

Ensure the platform is running via Docker Compose or local development servers:

```bash
# Start backend, postgres, redis, celery, and next.js frontend
docker compose up -d --build

# Run database migrations and seed realistic production telemetry
docker compose exec backend python -m app.scripts.seed
```

Verify services are healthy:
- Frontend: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Health & Metrics: http://localhost:8000/health, http://localhost:8000/metrics

---

## 2. Walkthrough Flow

### Step 1: Authentication & RBAC Personas (Frontend: `/login` & `/settings`)
1. Open http://localhost:3000/login.
2. Highlight the **Demo Persona Selector**:
   - **Admin** (`admin@example.com`): Full administrative permissions, service creation, user management.
   - **Staff SRE / Engineer** (`engineer@example.com`): Incident command, status progression, runbook editing, postmortem review.
   - **On-Call Engineer** (`oncall@example.com`): Alert triage, acknowledgment, mitigation.
   - **Viewer** (`viewer@example.com`): Read-only auditor session.
3. Login as **Admin** or **Staff SRE**. Explain to the interviewer that tokens are generated as stateless JWTs (HS256) accompanied by opaque refresh tokens with rotation and Redis revocation blacklist.

### Step 2: Operations Command Center (Frontend: `/`)
1. Inspect the live KPI ribbon:
   - **Active Incidents**: Highlighting active SEV1/SEV2 emergencies.
   - **MTTA (Mean Time to Acknowledge)**: Sub-5 minute target.
   - **MTTR (Mean Time to Resolve)**: Median and P95 resolution metrics.
   - **Alert Signal-to-Noise**: Demonstrates deduplication ratio (e.g. 25 alerts aggregated into active incidents).
2. Point out the **Live WebSocket Stream** badge (`LIVE STREAM`):
   - Whenever an incident is declared or transitioned, connected dashboards update dynamically without page refreshes.

### Step 3: Alert Ingestion & Idempotent Deduplication (Frontend: `/alerts` & Terminal)
1. Simulate an incoming monitoring alert from Prometheus/Datadog using `curl`:
   ```bash
   curl -X POST http://localhost:8000/api/v1/alerts \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: demo-key-001" \
     -d '{
       "service_id": "<PAYMENT_SERVICE_UUID>",
       "source": "prometheus",
       "severity": "CRITICAL",
       "title": "Payment API 5xx Surge",
       "description": "HTTP 500 error rate exceeded 35% on /v1/charges",
       "fingerprint": "pay-api-5xx-surge-prod",
       "metadata_json": {"error_rate": 35.2, "endpoint": "/v1/charges", "cluster": "us-east-1"}
     }'
   ```
2. **Interview Talking Point - Deduplication & Concurrency**:
   - Fire the exact same request 5 times rapidly.
   - Show how the database checks the unique `fingerprint` constraint within a transactional lock.
   - Instead of spamming 5 duplicate incidents into the on-call pager, the backend increments `occurrence_count` from 1 to 5, updates `last_seen`, and correlates with the existing open incident.
   - Replaying the same request with `Idempotency-Key: demo-key-001` returns the exact cached HTTP response without re-executing business logic.

### Step 4: Flagship Incident Command Center (Frontend: `/incidents/[id]`)
1. Click on the active **SEV1: Payment Gateway Outage** incident.
2. Inspect the **State Pipeline Ribbon**:
   - `DETECTED` → `TRIGGERED` → `ACKNOWLEDGED` → `INVESTIGATING` → `MITIGATING` → `RESOLVED` → `CLOSED`.
   - Explain how invalid transitions (e.g. jumping directly from `DETECTED` to `CLOSED`) are rejected with `409 Conflict` by the state machine in `app.domain.incidents`.
3. Walk through the multi-tab layout:
   - **Audit Timeline**: Immutable chronological log recording who changed status, who added comments, and when alerts arrived.
   - **AI Analysis & Hypothesis Engine**:
     - Click **"Run AI Root-Cause Analysis"**.
     - Point out the strict distinction between **Observed Facts** (corroborated from database logs and alerts) vs **Probable Hypotheses** (e.g. `HYPOTHESIS: Connection pool ceiling exceeded during sudden traffic spike`) vs **Remediation Steps** (e.g. `1. Run pg_stat_activity to inspect blocked queries. 2. Scale connection pool ceiling.`).
     - Highlight that the system provides a zero-dependency deterministic heuristic provider for offline demos and seamlessly switches to OpenAI GPT-4o when `OPENAI_API_KEY` is present.
   - **Correlated Alerts**: View all upstream telemetry linked by fingerprint.
   - **Contextual Service Logs**: View correlated log entries around the incident window with automated secret redaction (`[REDACTED_BEARER_TOKEN]`).
   - **Operational Runbook**: Linked emergency SOP and checklist for database pool triage.
   - **Collaborative Team Notes**: Real-time comment stream for incident responders.

### Step 5: Postmortem Generation & SRE Approval (Frontend: `/postmortems`)
1. Transition the incident from `MITIGATING` to `RESOLVED`.
2. Generate an AI-assisted blameless retrospective draft with 1 click.
3. Open http://localhost:3000/postmortems to inspect the generated report:
   - Executive Summary
   - Customer & Financial Impact
   - Chronological Timeline
   - 5-Whys Root Cause
   - Contributing Factors & Preventive Action Items
4. Walk through the review workflow (`DRAFT` → `REVIEW` → `APPROVED`) and demonstrate **Copy Markdown** for export to Notion/Confluence.

### Step 6: SRE Analytics & Reliability Reporting (Frontend: `/analytics`)
1. Navigate to http://localhost:3000/analytics.
2. Review mathematical reliability indicators:
   - MTTA mean and SLO compliance
   - MTTR mean, median, and P95 latencies
   - Service uptime availability rankings (e.g., Payment API 99.85% vs Order Service 99.98%)
   - Detected failure pattern clustering (e.g. repeated Redis cache stampedes or Kafka consumer lags).

---

## 3. Summary of Technical Highlights for the Interviewer

| Dimension | Engineering Implementation |
|---|---|
| **Architecture** | FastAPI Modular Monolith with clean domain separation (`app/domain`, `app/api`, `app/models`, `app/workers`). |
| **Concurrency & Deduplication** | Database-level unique constraints, advisory locking, SHA-256 idempotency cache. |
| **Async Tasks** | Celery + Redis for synthetic health probes, AI analysis background tasks, and periodic history pruning. |
| **Real-time** | WebSocket broadcast channels for instant dashboard and incident synchronization. |
| **AI Strategy** | Decoupled `LLMProvider` protocol, hybrid contextual retrieval, deterministic offline heuristic provider. |
| **Data Integrity** | SQLAlchemy 2.0 asyncpg, Alembic migrations, foreign key constraints with index optimization. |
| **Security & Auditing** | Argon2 password hashing, RBAC permission matrices, secret redaction, immutable audit timeline. |
