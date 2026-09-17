# Production Incident Management & AIOps Platform

A production-grade SRE and incident response platform built with **FastAPI**, **PostgreSQL 16**, **SQLAlchemy 2.0 (asyncpg)**, **Redis 7**, **Celery**, **WebSockets**, **Next.js 16 (App Router & Turbopack)**, and an extensible **AI/RAG Engine**.

Designed and implemented following real-world site reliability engineering standards, distributed systems concurrency patterns, immutable audit logging, blameless postmortem workflows, and deterministic reliability mathematics.

---

## System Architecture

```text
                                +------------------------------------------+
                                |      Next.js 16 SRE Command Center       |
                                |  (TypeScript, Tailwind CSS, Recharts)    |
                                +--------------------+---------------------+
                                                     |
                                   REST APIs (HTTP)  |  WebSockets (/ws/*)
                                                     v
+----------------------------------------------------+----------------------------------------------------+
|                                    FastAPI Modular Monolith                                      |
|                                                                                                  |
|  +--------------------+   +--------------------+   +--------------------+   +-----------------+  |
|  |    Auth & RBAC     |   |   Alert Ingestion  |   | Incident Lifecycle |   |   Service SRE   |  |
|  |  Argon2 + JWT +    |   |  Deduplication +   |   | Finite State DAG + |   |  Catalog, SLO,  |  |
|  |  Role Permissions  |   |  Fingerprint Hash  |   |  Audit Timeline    |   |  Health Probes  |  |
|  +--------------------+   +--------------------+   +--------------------+   +-----------------+  |
|                                                                                                  |
|  +--------------------+   +--------------------+   +--------------------+   +-----------------+  |
|  |    Log Explorer    |   |  AIOps RAG Engine  |   | Runbook Knowledge  |   | Postmortem Lib  |  |
|  |   Redaction + GIN  |   |  Facts vs Hypo +   |   | Step Procedures +  |   | 5-Whys + Action |  |
|  |   Keyword Search   |   |  Heuristic/OpenAI  |   | Execution Guides   |   | Item Lifecycle  |  |
|  +--------------------+   +--------------------+   +--------------------+   +-----------------+  |
+--------------------------+-------------------------------------+---------------------------------+
                           |                                     |
               Asyncpg Pool|                        Broker / PubSub|
                           v                                     v
             +---------------------------+             +---------------------------+
             |       PostgreSQL 16       |             |          Redis 7          |
             |   Relational Integrity,   |             |   Task Queue, WebSockets, |
             |   JSONB Telemetry, GIN,   |             |   Idempotency Caching,    |
             |   Advisory Lock Invariants|             |   Rate Limiting           |
             +---------------------------+             +-------------+-------------+
                                                                     |
                                                                     v
                                                       +---------------------------+
                                                       |   Celery Worker Cluster   |
                                                       |   - Periodic Health Probes|
                                                       |   - AI Async Analysis     |
                                                       |   - Daily History Cleanup |
                                                       +---------------------------+
```

---

## Core Engineering Capabilities

1. **State Machine & Incident Lifecycle**:
   - Strictly enforced directed acyclic graph (DAG):
     `DETECTED` $\to$ `TRIGGERED` $\to$ `ACKNOWLEDGED` $\to$ `INVESTIGATING` $\to$ `MITIGATING` $\to$ `RESOLVED` $\to$ `CLOSED`.
   - Invalid transitions or out-of-order mutations are rejected with `409 Conflict`.
   - Dedicated `reopen` endpoint with mandatory justification auditing.
   - Every mutation automatically generates an immutable `TimelineEvent` with actor attribution.

2. **Deduplication & Concurrency Control**:
   - Upstream SHA-256 fingerprint generation:
     $$\text{fingerprint} = \text{SHA-256}(\text{source} \parallel \text{service\_slug} \parallel \text{check\_name})$$
   - Database-enforced uniqueness constraints prevent race conditions during alert storms.
   - Incoming duplicate alerts atomically increment `occurrence_count` and update `last_seen` without duplicating active incidents.
   - Idempotency key tracking caches request hashes in Redis/PostgreSQL to prevent duplicate executions.

3. **Deterministic Severity Calculation**:
   - Multi-factor algorithmic scoring evaluates alert severity, service criticality, blast radius (affected service count), and customer error rate:
     - Score $\ge 7 \implies \text{SEV1}$ (Critical Outage)
     - Score $\ge 5 \implies \text{SEV2}$ (Major Degradation)
     - Score $\ge 3 \implies \text{SEV3}$ (Minor Incident)
     - Otherwise $\implies \text{SEV4}$ (Low Priority)

4. **Extensible AI & RAG Engine**:
   - Strict separation of concerns via the `LLMProvider` protocol:
     - **Observed Facts**: Grounded solely in database-verified logs and alerts.
     - **Probable Hypotheses**: Clear speculative root-cause hypotheses with confidence metrics.
     - **Remediation Actions**: Curated mitigation steps derived from indexed operational runbooks.
   - Out of the box, provides a zero-dependency **Deterministic Heuristic Engine** for offline demos and local testing, plus seamless integration with **OpenAI GPT-4o** when an API key is provided.

5. **Asynchronous Background Processing (Celery + Redis)**:
   - Automated periodic health checks against service `health_endpoint` URLs every 30 seconds.
   - Automatic alert and incident generation upon repeated probe failures (e.g. 5xx status codes, network timeouts).
   - Automated retention cleanup for historical health checks older than 7 days.

6. **Modern SRE Operations Dashboard (Next.js 16 App Router)**:
   - Live WebSocket connection status indicator (`LIVE STREAM`).
   - SRE Reliability Analytics: MTTA mean, MTTR percentiles (Mean, Median, P95), and alert-to-incident noise ratios.
   - Flagship Incident Command Center with multi-tab investigation views: Audit Timeline, AI Hypothesis, Correlated Alerts, Redacted Logs, Runbooks, and Comments.
   - Blameless Postmortem Library with markdown export.
   - Demo Persona Switcher (Admin, Staff SRE, On-Call Engineer, Viewer) for live interview demonstrations.

---

## Quick Start (Docker Compose)

### 1. Clone & Launch Containers
```bash
# Clone the repository
git clone https://github.com/example/production-incident-management.git
cd "production incident mng"

# Copy environment template
cp .env.example .env

# Build and start all 6 services
docker compose up -d --build
```

### 2. Seed Realistic Production Data
```bash
# Populate services, users, alerts, incidents, logs, and runbooks
docker compose exec backend python -m app.scripts.seed
```

### 3. Access Services
- **Frontend Dashboard**: [http://localhost:3000](http://localhost:3000)
- **Interactive OpenAPI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
- **Readiness Probe**: [http://localhost:8000/ready](http://localhost:8000/ready)
- **Prometheus Metrics**: [http://localhost:8000/metrics](http://localhost:8000/metrics)

---

## Demo Personas & Credentials

For local development and technical interviews:

| Persona | Email | Password | Role / Access Level |
|---|---|---|---|
| **Avery Morgan** | `admin@example.com` | `ChangeMe123!` | `ADMIN`: Full administrative control, service & user management. |
| **Riya Shah** | `engineer@example.com` | `ChangeMe123!` | `ENGINEER`: Staff SRE, incident command, postmortems. |
| **Jordan Lee** | `oncall@example.com` | `ChangeMe123!` | `ON_CALL_ENGINEER`: Primary responder, alert triage. |
| **Sam Taylor** | `viewer@example.com` | `ChangeMe123!` | `VIEWER`: Read-only stakeholder and compliance observer. |

---

## Local Development & Testing

### Backend (Python 3.11 / 3.12)
```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Run unit, integration, and concurrency tests
pytest -v --cov=app

# Start FastAPI server with live reload
uvicorn app.main:app --reload --port 8000
```

### Frontend (Next.js 16 + TypeScript)
```bash
cd frontend

# Install node dependencies
npm install

# Run TypeScript typecheck
npm run typecheck

# Build optimized production bundle
npm run build

# Start development server
npm run dev
```

---

## API Surface Overview

| Domain | Method | Endpoint | Description |
|---|---|---|---|
| **Auth** | `POST` | `/api/v1/auth/login` | Authenticate with email/password; returns JWT access + refresh tokens. |
| **Auth** | `POST` | `/api/v1/auth/refresh` | Rotate access token using valid refresh token. |
| **Users** | `GET` | `/api/v1/users/me` | Current authenticated user with roles and permissions. |
| **Users** | `GET` | `/api/v1/users` | List active users for incident assignment. |
| **Services** | `GET` | `/api/v1/services` | Service catalog with health status and criticality. |
| **Services** | `POST` | `/api/v1/services` | Register a new monitored service. |
| **Services** | `POST` | `/api/v1/services/{id}/health-check` | Trigger an immediate on-demand HTTP health probe. |
| **Alerts** | `GET` | `/api/v1/alerts` | Alert inbox with status and severity filters. |
| **Alerts** | `POST` | `/api/v1/alerts` | Ingest upstream monitoring alert with fingerprint deduplication. |
| **Alerts** | `POST` | `/api/v1/alerts/{id}/acknowledge` | Acknowledge alert and update responder metadata. |
| **Alerts** | `POST` | `/api/v1/alerts/{id}/suppress` | Suppress repetitive alert for specified duration. |
| **Alerts** | `POST` | `/api/v1/alerts/{id}/resolve` | Mark alert as resolved. |
| **Incidents** | `GET` | `/api/v1/incidents` | Incident explorer with multi-criteria filtering and pagination. |
| **Incidents** | `POST` | `/api/v1/incidents` | Declare new incident, calculate severity, broadcast via WS. |
| **Incidents** | `GET` | `/api/v1/incidents/{id}` | Detailed incident view with timeline, alerts, and comments. |
| **Incidents** | `POST` | `/api/v1/incidents/{id}/transition` | Execute state transition with strict DAG validation. |
| **Incidents** | `POST` | `/api/v1/incidents/{id}/assign` | Assign incident commander or responder. |
| **Incidents** | `POST` | `/api/v1/incidents/{id}/comments` | Append responder comment to discussion stream. |
| **Incidents** | `POST` | `/api/v1/incidents/{id}/reopen` | Reopen resolved/closed incident with required audit reason. |
| **Logs** | `GET` | `/api/v1/logs` | Query structured service logs with secret redaction. |
| **Runbooks** | `GET` | `/api/v1/runbooks` | Retrieve operational SOPs filtered by service or incident type. |
| **Postmortems** | `GET` | `/api/v1/postmortems` | Blameless retrospective library. |
| **Postmortems** | `PATCH` | `/api/v1/postmortems/{id}` | Update postmortem sections or approve report. |
| **AI / AIOps** | `POST` | `/api/v1/ai/incidents/{id}/analysis` | Execute contextual AI root-cause analysis. |
| **AI / AIOps** | `POST` | `/api/v1/ai/incidents/{id}/postmortem-draft` | Generate evidence-grounded postmortem draft. |
| **Analytics** | `GET` | `/api/v1/analytics/summary` | SRE reliability metrics: MTTA, MTTR, availability, patterns. |

---

## Architectural Deep-Dives

- [Technical Demo Script & Interview Walkthrough](docs/demo-scenario.md)
- [Architecture Decision Records (ADRs) & Trade-Offs](docs/engineering-decisions.md)
- [System Architecture Specification](architecture.md)
- [Database Schema & Indexing Invariants](database-schema.md)
- [Complete REST API Design](api-design.md)
