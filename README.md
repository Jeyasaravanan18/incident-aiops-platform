# Incident AIOps & SRE Reliability Platform

[![CI](https://github.com/Jeyasaravanan18/incident-aiops-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/Jeyasaravanan18/incident-aiops-platform/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16%20(pgvector)-336791.svg)](https://www.postgresql.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-7%20(PubSub%20%2B%20ZSET)-DC382D.svg)](https://redis.io/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16%20(Turbopack)-black.svg)](https://nextjs.org/)

A production-grade site reliability engineering (SRE) and incident response platform featuring **PostgreSQL 16** with **pgvector**, **SQLAlchemy 2.0 async**, **Redis 7** (sliding-window rate limiting & pub/sub event fan-out), **Celery**, and a **hybrid RAG pipeline** (dense embeddings + full-text search with Reciprocal Rank Fusion) for grounded incident mitigation.

---

## Architecture Diagram

```mermaid
flowchart TD
    Client[Next.js 16 Web Console / SRE Operators] -->|REST HTTP / JWT| API[FastAPI Monolith]
    Client <-->|WebSockets| WSMgr[WebSocket Manager]
    
    subgraph Data Layer
        API -->|Async Sessions / asyncpg| PG[(PostgreSQL 16 + pgvector)]
        API -->|Atomic ZSET Rate Limit| Redis[(Redis 7)]
        WSMgr <-->|Pub/Sub Event Fan-Out| Redis
    end

    subgraph Relational & Vector Storage
        PG --> Alerts[alerts: SHA-256 Fingerprint Upsert]
        PG --> Incidents[incidents: DAG State Machine & Partial Index]
        PG --> Knowledge[knowledge_chunks: HNSW Vector + tsvector GIN]
        PG --> Analytics[SQL Analytics: MTTA/MTTR FILTER & PERCENTILE_CONT]
    end

    subgraph Background Processing
        Redis -->|Task Broker| CeleryWorker[Celery Worker Cluster]
        CeleryBeat[Celery Beat Scheduler] -->|Periodic Crons| Redis
        CeleryWorker -->|Async Health Probes & AI Analysis| PG
    end

    subgraph RAG Pipeline
        Knowledge --> Retrieval[Hybrid Retrieval: Cosine Top-K + tsvector FTS]
        Retrieval --> RRF[Reciprocal Rank Fusion k=60]
        RRF --> Grounding[Grounded Prompt & Citation Validator]
        Grounding --> LLM[Gemini 1.5 Flash / Contextual Heuristic]
    end
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
6. **Hybrid RAG Pipeline with Citation Grounding**:
   - Indexes past runbooks, postmortems, and incident logs into `knowledge_chunks` with 768-dimensional embeddings and PostgreSQL `tsvector` generated columns.
   - Fuses dense vector cosine similarity and full-text search rankings via **Reciprocal Rank Fusion (RRF)**.
   - Validates model output against strict Pydantic schemas with automated retry loops (up to 2 retries) and programmatically verifies that 100% of generated citations exist in the retrieved knowledge set.

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

## Environment Variables

Copy `.env.example` to `.env` and configure your local settings:

| Variable | Description | Required | Example |
| :--- | :--- | :---: | :--- |
| `DATABASE_URL` | PostgreSQL async connection string | Yes | `postgresql+asyncpg://postgres:postgres@localhost:5432/incident_aiops` |
| `SYNC_DATABASE_URL` | PostgreSQL sync connection string (Alembic / Celery) | Yes | `postgresql://postgres:postgres@localhost:5432/incident_aiops` |
| `REDIS_URL` | Redis instance connection string | Yes | `redis://localhost:6379/0` |
| `JWT_SECRET` | Secret key for JWT signature (min 16 chars) | Yes | `development-jwt-secret-min-16-characters` |
| `JWT_ALGORITHM` | JWT cryptographic signing algorithm | No | `HS256` |
| `GEMINI_API_KEY` | Google Gemini API key (defaults to deterministic fake if unset) | No | `AIzaSy...` |
| `GEMINI_MODEL` | Gemini LLM model identifier | No | `gemini-1.5-flash` |
| `CORS_ORIGINS` | Permitted cross-origin endpoints | No | `http://localhost:3000` |

---

## How to Run

### 1. Docker Compose (Full Stack)
```bash
# Clone the repository
git clone https://github.com/Jeyasaravanan18/incident-aiops-platform.git
cd incident-aiops-platform

# Set up environment variables
cp .env.example .env

# Start PostgreSQL, Redis, Backend, Celery Worker, and Celery Beat
docker compose up -d

# Verify system health
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### 2. Local Development Setup
```bash
# 1. Start Postgres and Redis
docker compose up -d postgres redis

# 2. Set up Python virtual environment
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Run database migrations
alembic upgrade head

# 4. Seed database with synthetic data (100k logs, 2k incidents)
python -m app.scripts.seed_synthetic

# 5. Run the development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Running Automated Tests & Evaluation
```bash
# Run code format and lint checks
ruff check backend eval
black --check backend eval

# Run full pytest suite (67 passed, 65% coverage)
pytest backend/tests/ -v

# Run RAG evaluation harness (regenerates eval/results.md)
make eval  # or: python backend/scripts/run_eval.py
```

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

## Limitations & Honest Engineering Constraints

- **Synthetic Data**: Benchmarking was executed on 100,000 synthetic log rows and 2,012 synthetic incidents generated with deterministic distributions. While realistic in schema and concurrency volume, real-world customer workloads may exhibit different log cardinality.
- **Single-Node Docker Deployment**: The included `docker-compose.yml` runs a single PostgreSQL and Redis node. Multi-region high availability (Patroni, Redis Sentinel) is documented in architecture guides but not orchestrated locally.
- **Offline AI Fallback**: When `GEMINI_API_KEY` is omitted, the platform uses a deterministic semantic hash embedding provider and contextual heuristic rule engine to ensure tests, CI, and local demos pass reliably without external network dependencies.

---

## Documentation Links

- [docs/EVIDENCE.md](file:///c:/Users/rsury/OneDrive/Desktop/production%20incident%20mng/docs/EVIDENCE.md) — Line-by-line verification audit mapping every capability to tests.
- [docs/WALKTHROUGH.md](file:///c:/Users/rsury/OneDrive/Desktop/production%20incident%20mng/docs/WALKTHROUGH.md) — Codebase architecture walkthrough and deep-dive technical FAQ.
- [docs/performance.md](file:///c:/Users/rsury/OneDrive/Desktop/production%20incident%20mng/docs/performance.md) — Raw `EXPLAIN (ANALYZE, BUFFERS)` execution plans.
- [docs/schema.md](file:///c:/Users/rsury/OneDrive/Desktop/production%20incident%20mng/docs/schema.md) — Entity-relationship diagram (Mermaid) and constraint definitions.
- [eval/results.md](file:///c:/Users/rsury/OneDrive/Desktop/production%20incident%20mng/eval/results.md) — RAG evaluation metrics and defect postmortems.
