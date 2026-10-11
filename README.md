# Incident AIOps & SRE Reliability Platform

[![CI](https://github.com/Jeyasaravanan18/incident-aiops-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/Jeyasaravanan18/incident-aiops-platform/actions/workflows/ci.yml)
[![Vercel Deployment](https://img.shields.io/badge/Vercel-Frontend%20(Edge)-000000.svg?logo=vercel&logoColor=white)](https://incident-aiops-frontend.vercel.app)
[![Render Deployment](https://img.shields.io/badge/Render-Backend%20(Docker)-46E3B7.svg?logo=render&logoColor=black)](https://render.com)
[![Next.js 16](https://img.shields.io/badge/Next.js-16%20(App%20Router)-black.svg?logo=next.js)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16%20(pgvector)-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis 7](https://img.shields.io/badge/Redis-7%20(PubSub%20%2B%20ZSET)-DC382D.svg?logo=redis&logoColor=white)](https://redis.io/)
[![Google Gemini](https://img.shields.io/badge/AI-Gemini%202.5%20Flash-4285F4.svg?logo=google&logoColor=white)](https://ai.google.dev/)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg?logo=python&logoColor=white)](https://www.python.org/)

An enterprise-grade Site Reliability Engineering (SRE) and Incident Response platform built with a modern cloud-decoupled stack: **Next.js 16 on Vercel Edge**, **FastAPI on Render**, **PostgreSQL 16 (pgvector + tsvector)**, **Redis 7** (sliding-window rate limiting & distributed WebSocket pub/sub fan-out), and a **Hybrid RAG Pipeline with Google Gemini 2.5 Flash** for grounded incident root cause analysis.

---

## Live Production Links & Demo Credentials

| Resource | URL | Status / Notes |
| :--- | :--- | :--- |
| **Frontend Web Console** | [https://incident-aiops-frontend.vercel.app](https://incident-aiops-frontend.vercel.app) | Next.js 16 App Router on Vercel |
| **Backend API (Render)** | [https://incident-aiops-backend.onrender.com](https://incident-aiops-backend.onrender.com) | FastAPI container on Render |
| **API Health Check** | [https://incident-aiops-backend.onrender.com/health](https://incident-aiops-backend.onrender.com/health) | Returns `{"status": "ok"}` |
| **Readiness & DB Probe** | [https://incident-aiops-backend.onrender.com/ready](https://incident-aiops-backend.onrender.com/ready) | Verifies PostgreSQL and Redis health |
| **Interactive API Docs** | [https://incident-aiops-backend.onrender.com/docs](https://incident-aiops-backend.onrender.com/docs) | Swagger / OpenAPI Explorer |

### Pre-Seeded Enterprise Demo Accounts

The database comes pre-seeded with multi-role SRE test users (passwords: `ChangeMe123!`):

| Role | Email Address | Password | Permissions & Scope |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin@example.com` | `ChangeMe123!` | Full administrative access, service catalog edits, user roles |
| **Staff SRE / Engineer** | `engineer@example.com` | `ChangeMe123!` | Incident transitions, runbook edits, root-cause postmortems |
| **Primary On-Call** | `oncall@example.com` | `ChangeMe123!` | Alert acknowledgment, incident mitigation, live triage |
| **Viewer** | `viewer@example.com` | `ChangeMe123!` | Read-only analytics, health telemetry, postmortem viewing |

---

## Production Cloud Architecture

```mermaid
flowchart TD
    subgraph VercelEdge["Vercel Global Edge Network"]
        Client["Next.js 16 Web Console<br/>(React 19, TailwindCSS, Recharts)"]
        WSClient["WebSocket Client<br/>(Auto Reconnect over wss://)"]
    end

    subgraph RenderCloud["Render Cloud Platform"]
        Ingress["Render TLS Termination & Load Balancer"]
        API["FastAPI Backend Monolith<br/>(Python 3.12, Uvicorn, Docker)"]
        WSMgr["WebSocket Manager<br/>(Distributed Broadcast)"]
        CeleryWorker["Celery Worker Cluster<br/>(Async Tasks & Telemetry)"]
        
        subgraph DataLayer["Relational & Cache Tier"]
            PG[("PostgreSQL 16 Managed DB<br/>• pgvector 768-dim HNSW<br/>• tsvector GIN Full-Text<br/>• Advisory XACT Locks<br/>• DAG State Machine")]
            Redis[("Redis 7<br/>• ZSET Sliding Rate Limiter<br/>• Pub/Sub Event Fan-Out<br/>• Celery Task Queue")]
        end
    end

    subgraph GoogleAI["Google Cloud AI"]
        Gemini["Google Gemini 2.5 Flash<br/>(Structured Output + 100% Citation Grounding)"]
    end

    Client -->|"HTTPS REST / Bearer JWT"| Ingress
    WSClient <-->|"wss:// Secure WebSockets"| Ingress
    Ingress --> API
    Ingress <--> WSMgr

    API -->|"Async Sessions (asyncpg)"| PG
    API -->|"Atomic Rate Limiting"| Redis
    WSMgr <-->|"Pub/Sub Channels"| Redis
    CeleryWorker -->|"Task Broker"| Redis
    CeleryWorker -->|"Health Probes"| PG

    API -->|"Hybrid RRF RAG"| Gemini
```

---

## Verified Engineering Capabilities

1. **Unified Relational Core (PostgreSQL 16 & SQLAlchemy 2.0 Async)**:
   - Zero split-brain architecture. Powered completely by `asyncpg` and SQLAlchemy 2.0 async sessions.
   - Database-level CHECK constraints enforce valid timestamps (`acknowledged_at >= created_at`, `resolved_at >= created_at`, `occurrence_count >= 1`).
2. **Advisory Locks & Concurrency Control**:
   - Alert storms for any service acquire `pg_advisory_xact_lock(hashtext(CAST(:service_id AS text)))` to ensure concurrent alerts spawn exactly one active incident.
   - Status mutations lock the target incident with `SELECT ... FOR UPDATE`, strictly validating transitions against a Directed Acyclic Graph (DAG) state machine and rejecting conflicting changes with HTTP `409 Conflict`.
3. **Atomic Alert Deduplication**:
   - Normalizes titles, service IDs, and labels into a server-side SHA-256 fingerprint.
   - Ingests via atomic `INSERT ... ON CONFLICT (fingerprint) DO UPDATE SET occurrence_count = occurrence_count + 1, last_seen_at = now()`. Tested and proven with 50 concurrent alert ingestions collapsing to 1 database row.
4. **Pure SQL Analytics Engine**:
   - Replaced application-level loops with database calculations:
     - **MTTA & MTTR**: `AVG(...) FILTER (...)` grouped by service and severity.
     - **P50 / P95 Durations**: `PERCENTILE_CONT(...) WITHIN GROUP`.
     - **Zero-Filled Daily Trends**: `generate_series` with `LEFT JOIN` on `date_trunc('day', created_at)`.
     - **State Durations**: Window function `LAG()` over timeline events.
5. **Redis Sliding-Window Rate Limiter & Pub/Sub Fan-Out**:
   - Atomic rolling-window rate limiting on login and alert ingestion using Redis Sorted Sets (`ZSET`).
   - Distributed WebSocket broadcast cluster using Redis Pub/Sub channels to fan out live incidents across multiple backend instances.
   - Graceful fallback to `fakeredis` in single-container or test configurations.
6. **Hybrid RAG Pipeline with Citation Grounding**:
   - Indexes past runbooks, postmortems, and incident logs into `knowledge_chunks` with 768-dimensional embeddings and PostgreSQL `tsvector` generated columns.
   - Fuses dense vector cosine similarity and full-text search rankings via **Reciprocal Rank Fusion (RRF $k=60$)**.
   - Validates model output against strict Pydantic schemas with automated retry loops and programmatically verifies that 100% of generated citations exist in the retrieved knowledge set.

---

## Information Retrieval & Generation Benchmarks

Evaluated over **42 labeled production incident queries** and **20 diverse generation scenarios** using the automated evaluation harness (`make eval`):

| Retrieval Strategy | Recall@3 | Recall@5 | MRR (Mean Reciprocal Rank) | Notes |
| :--- | :---: | :---: | :---: | :--- |
| **PostgreSQL Full-Text Search (Keyword)** | **1.000** | **1.000** | **0.976** | `tsvector` with `websearch_to_tsquery` and `ts_rank_cd` |
| **Dense Vector Search (Vector only)** | **1.000** | **1.000** | **0.849** | Cosine similarity ranking over 768-dim embeddings |
| **Hybrid Search (Reciprocal Rank Fusion)** | **1.000** | **1.000** | **0.964** | Fused RRF: $RRF(d) = \sum \frac{1}{60 + \text{rank}_i}$ |

| Generation & Grounding Metric | Measured Result | Target | Criteria |
| :--- | :---: | :---: | :--- |
| **Post-Retry JSON Schema Valid Rate** | **100.0%** | 100% | Valid structured schema validated via Pydantic |
| **Citation Grounding Rate** | **100.0%** | 100% | 100% of citations strictly match retrieved chunk UUIDs |
| **P50 Latency (Offline Test Mode)** | **0.14 ms** | < 500 ms | Median processing time per incident analysis |
| **P95 Latency (Offline Test Mode)** | **0.29 ms** | < 1500 ms | 95th percentile latency |

*Full evaluation report available at [eval/results.md](file:///c:/Users/rsury/OneDrive/Desktop/production%20incident%20mng/eval/results.md).*

---

## SQL Performance Benchmarks (`EXPLAIN ANALYZE`)

Measured against **100,000 synthetic log rows** and **2,012 synthetic incidents** seeded via `app.scripts.seed_synthetic`:

| Target Query | Unindexed Scan | Indexed Scan | Speedup Factor | Buffers & Planning Impact |
| :--- | :---: | :---: | :---: | :--- |
| **Q1: Log Full-Text Search** (`search_vector @@ 'database \| timeout'`) | **173.03 ms** | **36.60 ms** | **4.73x** | Bitmap Index Scan on `ix_log_entries_search_vector_gin`. Cost dropped from 5,784 to 144. |
| **Q2: MTTR & P95 by Service** (`service_id` + `resolved_at`) | **2.86 ms** | **0.58 ms** | **4.91x** | Bitmap Index Scan on `ix_incidents_service_id`. Filter removed 1,893 rows in seq scan. |
| **Q3: Active Incidents per Service** (Partial Index) | Cost: 105 | Cost: 78 | **Optimized** | Partial index `ix_incidents_open_per_service` touches only 2 buffer pages. |

*Full execution plans and buffers recorded in [docs/performance.md](file:///c:/Users/rsury/OneDrive/Desktop/production%20incident%20mng/docs/performance.md).*

---

## Cloud Deployment Guide

### 1. Backend & Database on Render (Automated)

The repository provides a pre-configured [render.yaml](file:///c:/Users/rsury/OneDrive/Desktop/production%20incident%20mng/render.yaml) Blueprint:

1. In your **Render Dashboard**, select **New +** > **Blueprint**.
2. Connect this repository: `https://github.com/Jeyasaravanan18/incident-aiops-platform`.
3. Render automatically provisions:
   - **PostgreSQL 16 Database** (`incident-aiops-db`)
   - **Docker Web Service** (`incident-aiops-backend`) with automatic migrations & database seeding via `start.sh`.
4. Add your optional **Gemini API Key**: `GEMINI_API_KEY=AIzaSy...`.
5. Once deployed, copy your backend URL (`https://incident-aiops-backend.onrender.com`).

### 2. Frontend Web Console on Vercel

1. In your **Vercel Dashboard**, click **Add New...** > **Project**.
2. Import the GitHub repository.
3. In Project Settings:
   - **Root Directory**: `frontend` *(⚠️ Crucial: select the `frontend` subfolder)*.
   - **Framework Preset**: `Next.js`.
4. Add Environment Variable:
   - `NEXT_PUBLIC_API_BASE_URL` = `https://incident-aiops-backend.onrender.com` *(no trailing slash)*.
5. Click **Deploy**.
6. Set `CORS_ORIGINS` in Render to match your Vercel URL (`https://incident-aiops-frontend.vercel.app`).

### 3. Local Full-Stack Run with Docker Compose

```bash
# 1. Clone repository
git clone https://github.com/Jeyasaravanan18/incident-aiops-platform.git
cd incident-aiops-platform

# 2. Setup environment variables
cp .env.example .env

# 3. Start PostgreSQL, Redis, Backend, Celery, and Frontend
docker compose up -d

# 4. Verify system health
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

---

## Environment Variables Reference

| Variable | Description | Where It Lives | Required | Example |
| :--- | :--- | :---: | :---: | :--- |
| `DATABASE_URL` | PostgreSQL async connection string | Render / `.env` | Yes | `postgresql+asyncpg://user:pass@host:5432/incident_aiops` |
| `SYNC_DATABASE_URL` | PostgreSQL sync connection string (Alembic) | Render / `.env` | Auto | `postgresql://user:pass@host:5432/incident_aiops` |
| `REDIS_URL` | Redis instance connection string | Render / `.env` | No | `redis://localhost:6379/0` *(defaults to FakeRedis if unset)* |
| `JWT_SECRET` | Secret key for JWT cryptographic signatures | Render / `.env` | Yes | `min-32-chars-long-secure-random-secret` |
| `CORS_ORIGINS` | Permitted cross-origin endpoints | Render / `.env` | Yes | `https://incident-aiops-frontend.vercel.app,http://localhost:3000` |
| `GEMINI_API_KEY` | Google Gemini API key | Render / `.env` | No | `AIzaSy...` *(falls back to deterministic heuristic if omitted)* |
| `GEMINI_MODEL` | Gemini LLM model identifier | Render / `.env` | No | `gemini-2.5-flash` |
| `AUTO_SEED` | Automatically seeds demo data on container boot | Render / `.env` | No | `true` |
| `NEXT_PUBLIC_API_BASE_URL` | Backend API URL for frontend client | Vercel | Yes | `https://incident-aiops-backend.onrender.com` |

---

## Public REST API Overview

All routes are mounted under `/api/v1`:

- **Auth** (`/api/v1/auth`): `/login`, `/refresh`, `/me`, `/register` (Argon2id + JWT tokens).
- **Incidents** (`/api/v1/incidents`): `/`, `/{id}`, `/{id}/transition` (DAG state machine), `/{id}/assign`, `/{id}/comments`.
- **Alerts** (`/api/v1/alerts`): `/` (ingestion with SHA-256 deduplication), `/{id}/acknowledge`.
- **Services** (`/api/v1/services`): `/` (catalog CRUD), `/{id}/health` (SLO & probe telemetry).
- **Logs** (`/api/v1/logs`): `/` (ingestion with automated credential redaction & tsvector query).
- **Runbooks** (`/api/v1/runbooks`): `/` (knowledge base articles with GIN index search).
- **Postmortems** (`/api/v1/postmortems`): `/` (blameless root cause analysis & action items).
- **Analytics** (`/api/v1/analytics`): `/summary`, `/breakdown` (MTTA/MTTR), `/noisy-alerts`.
- **AI & RAG** (`/api/v1/ai`): `/incidents/{id}/analyze` (hybrid RAG incident cause & mitigation).
- **Notifications** (`/api/v1/notifications`): `/`, `/{id}/read` (in-app alert updates).

---

## Documentation Links

- [architecture.md](file:///c:/Users/rsury/OneDrive/Desktop/production%20incident%20mng/architecture.md) — System Architecture, Cloud Topology, and Decision Matrix.
- [docs/deployment.md](file:///c:/Users/rsury/OneDrive/Desktop/production%20incident%20mng/docs/deployment.md) — Comprehensive Vercel & Render production deployment guide.
- [docs/EVIDENCE.md](file:///c:/Users/rsury/OneDrive/Desktop/production%20incident%20mng/docs/EVIDENCE.md) — Line-by-line verification audit mapping every capability to tests.
- [docs/WALKTHROUGH.md](file:///c:/Users/rsury/OneDrive/Desktop/production%20incident%20mng/docs/WALKTHROUGH.md) — Codebase architecture walkthrough and deep-dive technical FAQ.
- [docs/performance.md](file:///c:/Users/rsury/OneDrive/Desktop/production%20incident%20mng/docs/performance.md) — Raw `EXPLAIN (ANALYZE, BUFFERS)` execution plans.
- [docs/schema.md](file:///c:/Users/rsury/OneDrive/Desktop/production%20incident%20mng/docs/schema.md) — Entity-relationship diagram (Mermaid) and constraint definitions.
- [eval/results.md](file:///c:/Users/rsury/OneDrive/Desktop/production%20incident%20mng/eval/results.md) — RAG evaluation metrics and defect postmortems.
