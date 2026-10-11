# System Architecture & Engineering Deep-Dive

This document provides a comprehensive technical walkthrough of every module in the platform, accompanied by an architectural decisions FAQ detailing the engineering rationale and trade-offs drawn directly from the codebase.

---

## 1. Architectural Module Walkthrough

### `app/core/` — Infrastructure Foundations
- **`config.py`**: Pydantic `BaseSettings` that fails fast on startup if `DATABASE_URL` or `JWT_SECRET` are missing or malformed. Reads secrets strictly from environment variables without hardcoded fallbacks.
- **`database.py`**: Initializes SQLAlchemy 2.0 `create_async_engine` using `asyncpg` with a pooled connection strategy (`pool_size=20`, `max_overflow=10`). Exposes the async dependency `get_session` used by every router.
- **`security.py`**: Cryptographic routines using Argon2id for one-way password hashing (`PasswordHasher`) and PyJWT for signed access and refresh tokens with expiration and token-type claims.
- **`redis.py`**: Manages the Redis connection pool. Implements an atomic sliding-window rate limiter using Redis Sorted Sets (`ZSET`), executing `ZREMRANGEBYSCORE`, `ZCARD`, and `ZADD` atomically. Falls back to in-memory `fakeredis` during offline tests.
- **`middleware.py`**: Injects unique `X-Request-ID` headers across all HTTP requests for distributed log tracing.

### `app/domain/` — Pure Business Logic (Framework-Agnostic)
- **`incidents.py`**: Enforces the incident finite state machine as a Directed Acyclic Graph (`DETECTED` $\to$ `TRIGGERED` $\to$ `ACKNOWLEDGED` $\to$ `INVESTIGATING` $\to$ `MITIGATING` $\to$ `RESOLVED` $\to$ `CLOSED`). Computes transition timestamps and validates reopening constraints. Implements deterministic multi-factor severity scoring (alert severity, service criticality, blast radius).
- **`alerts.py`**: Normalizes alert attributes (service ID, title, filtered labels) and computes server-side SHA-256 fingerprint hashes.
- **`chunking.py`**: Splits runbooks, postmortems, and incident logs into overlapping text passages (default 400 tokens with 50-token overlap) for dense embedding and vector search.
- **`redaction.py`**: Regex masking engine that redacts API keys, JWTs, Bearer tokens, passwords, and private certificates from log messages and nested metadata prior to database persistence.

### `app/models/` — Database Schema & ORM
- Declarative models utilizing SQLAlchemy 2.0 mapped columns:
  - **`knowledge.py`**: `KnowledgeChunk` containing source metadata, text passages, `vector(768)` embeddings, and a PostgreSQL `tsvector` generated column (`Computed("to_tsvector('english', coalesce(content, ''))", persisted=True)`).
  - **`alert.py`**: `Alert` model with unique constraint on `fingerprint`, server-enforced `occurrence_count`, and CHECK constraint `ck_alerts_occurrence_positive`.
  - **`incident.py`**: `Incident` model featuring status/severity enums, partial index `ix_incidents_open_per_service` on active incidents, and CHECK constraints `ck_incidents_ack_after_created` and `ck_incidents_res_after_created`.
  - **`log.py`**: `LogEntry` model with GIN full-text index `ix_log_entries_search_vector_gin`.

### `app/repositories/` — Data Access & SQL Execution
- Isolates complex SQL from API routing:
  - **`alert_repo.py`**: Executes atomic `INSERT ... ON CONFLICT (fingerprint) DO UPDATE` to collapse duplicate alerts and increment occurrence counts.
  - **`incident_repo.py`**: Acquires PostgreSQL transaction advisory locks (`SELECT pg_advisory_xact_lock(hashtext(CAST(:service_id AS text)))`) during alert storm auto-escalations, and executes `SELECT ... FOR UPDATE` row-level locks on status transitions.
  - **`analytics_repo.py`**: Executes pure SQL aggregations for MTTA/MTTR (`AVG(...) FILTER (...)`), P50/P95 durations (`PERCENTILE_CONT(...) WITHIN GROUP`), zero-filled daily trends (`generate_series`), status transition durations (`LAG()`), and noisy alert identification (`GROUP BY ... HAVING`).
  - **`knowledge_repo.py`**: Manages document re-indexing, full-text tsquery search (`websearch_to_tsquery`), and dense vector similarity queries.

### `app/services/` — AI & Hybrid RAG Engine
- **`embeddings.py`**: Defines the `EmbeddingProvider` interface. Contains `GeminiEmbeddingProvider` for live API calls and `DeterministicFakeEmbeddingProvider` for offline test suites and CI.
- **`rag_retrieval.py`**: Implements hybrid search combining dense vector cosine similarity with full-text search (`tsvector`), fusing rankings using Reciprocal Rank Fusion (RRF with $k=60$).
- **`rag_generation.py`**: Coordinates structured prompt generation, JSON schema validation via Pydantic, automated retry loops (up to 2 retries with feedback), strict citation grounding validation against retrieved chunks, and automatic fallback to contextual heuristic analysis.

### `app/websocket/` — Real-Time Event Fan-Out
- **`manager.py`**: Manages active WebSocket connections per incident and dashboard channel. Connects to Redis Pub/Sub so events broadcast from any worker or server instance are published to the Redis channel and delivered across all backend server nodes.

### `app/workers/` — Asynchronous Celery Tasks
- **`tasks.py`**: Runs scheduled background tasks: periodic health probes every 30 seconds (`probe_service_health`), async AI incident analysis (`run_ai_analysis`), historical health record cleanup (`cleanup_old_health_records`), and knowledge re-indexing (`reindex_knowledge_chunk`). Standardized on async session contexts (`async with SessionLocal() as session: ...`) inside `asyncio.run()`.

---

## 2. Architecture & Design Decisions Deep-Dive (Technical FAQ)

### 1. Unified Storage: Why eliminate MongoDB in favor of a single PostgreSQL database?
> **Answer:** The original codebase had a "split-brain" architecture where API routers queried MongoDB while Celery workers and migrations ran on PostgreSQL. This caused inconsistent data, cross-database sync failures, and Celery crashes when sessions were mismatched. Migrating to PostgreSQL 16 with SQLAlchemy 2.0 async and `asyncpg` unified all entities under ACID transactional guarantees, eliminated redundant infrastructure, enabled advisory locks for distributed synchronization, and allowed relational joins across alerts, incidents, and audit timelines.

### 2. Concurrency Control: How do you prevent duplicate incidents during an alert storm?
> **Answer:** When hundreds of concurrent alerts hit the system for a degraded service, we use a PostgreSQL transaction-scoped advisory lock: `SELECT pg_advisory_xact_lock(hashtext(CAST(:service_id AS text)))`. This lock serializes incident creation per service within the database transaction without deadlocking table rows. The first transaction creates the incident; concurrent transactions immediately detect the existing open incident and attach their alerts to it.

### 3. Locking Strategy: What is the difference between an advisory lock and a row-level lock?
> **Answer:** Row-level locks (`SELECT FOR UPDATE`) require a specific row to already exist in a table before locking it. When checking if an incident exists for a service, no row exists yet during the first alert, leading to race conditions where multiple transactions attempt to insert. An advisory lock (`pg_advisory_xact_lock`) locks an application-defined integer key (the 32-bit hash of the service ID) inside PostgreSQL's lock manager without touching table storage. It automatically releases when the transaction commits or rolls back.

### 4. Alert Ingestion: How does alert deduplication work under high concurrency?
> **Answer:** Alerts are normalized and fingerprinted server-side using SHA-256 over `(service_id, normalized_title, severity_independent_labels)`. We execute an atomic SQL upsert:
> ```sql
> INSERT INTO alerts (...) VALUES (...)
> ON CONFLICT (fingerprint) DO UPDATE
> SET occurrence_count = alerts.occurrence_count + 1, last_seen_at = now()
> RETURNING id, incident_id, occurrence_count;
> ```
> In tests with 50 concurrent requests for the exact same alert, the database collapses them into exactly 1 row with `occurrence_count == 50`.

### 5. State Machine: How do you prevent race conditions during incident status transitions?
> **Answer:** Before executing a state transition, the repository executes `SELECT ... FOR UPDATE` to lock the target incident row. We evaluate the state transition against our Directed Acyclic Graph (DAG) state machine. If an invalid or conflicting transition is attempted (e.g. attempting to close an incident that another responder just set to investigating), the transaction rejects the move and returns an HTTP `409 Conflict`.

### 6. Hybrid RAG: Why implement Reciprocal Rank Fusion (RRF) instead of pure dense vector search?
> **Answer:** Dense vector search maps text into continuous embedding space, which is great for semantic synonyms but frequently fails on exact technical tokens like error codes (`HTTP 504`, `OOMKilled 137`, `pg_terminate_backend`). Full-text search (`tsvector`) excels at exact keyword matching. Reciprocal Rank Fusion merges rankings from both channels using:
> $$RRF(d) = \sum_{m \in \{\text{vec}, \text{fts}\}} \frac{1}{60 + \text{rank}_m(d)}$$
> This ensures exact error codes receive an immediate rank boost while semantic context surfaces relevant runbooks even when different terminology is used.

### 7. AI Grounding: How do you prevent LLMs from hallucinating citations in incident analyses?
> **Answer:** We enforce a strict two-stage grounding check:
> 1. In the structured prompt, the LLM is restricted to citing only chunk UUIDs present in the retrieved context block.
> 2. Post-generation, our Python validator checks `set(output.citations).issubset(retrieved_chunk_ids)`. If an invalid citation is detected, the pipeline feeds the validation error back to the model in a retry loop (up to 2 retries). If retries fail, it falls back to the deterministic heuristic provider and marks `fallback_used=True` in the database audit log.

### 8. Rate Limiting: How does the Redis sliding-window rate limiter work?
> **Answer:** Rather than a simple counter with boundary reset spikes, we use Redis Sorted Sets (`ZSET`). For each incoming request identified by IP or user ID:
> 1. We remove entries older than the rolling window: `ZREMRANGEBYSCORE key 0 (now - window)`.
> 2. We count the remaining requests: `ZCARD key`.
> 3. If the count exceeds the threshold, we reject with HTTP `429 Too Many Requests`.
> 4. Otherwise, we record the request timestamp: `ZADD key now uuid`.
> All operations run within an atomic pipeline.

### 9. Real-Time Fan-Out: How do you scale WebSockets horizontally across multiple backend servers?
> **Answer:** If multiple FastAPI instances run behind a load balancer, client WebSockets are distributed across servers. When an alert or incident event is generated on Server A, Server A publishes the event payload to a Redis channel (`incident_events`). All server instances subscribe to this channel via an async worker loop; upon receiving the message, each server broadcasts it to its locally connected WebSocket clients.

### 10. SQL Analytics: How are MTTA and MTTR calculated in SQL rather than application loops?
> **Answer:** Instead of pulling thousands of rows into Python memory, we execute database-level aggregations:
> ```sql
> SELECT
>   AVG(EXTRACT(EPOCH FROM (acknowledged_at - created_at)) / 60)
>     FILTER (WHERE acknowledged_at IS NOT NULL) AS mtta_minutes,
>   AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 60)
>     FILTER (WHERE resolved_at IS NOT NULL) AS mttr_minutes
> FROM incidents
> WHERE created_at >= :cutoff;
> ```
> PostgreSQL's `FILTER` clause computes the averages in a single sequential scan or index pass.

### Q11: Why did you use `PERCENTILE_CONT ... WITHIN GROUP` for P95 MTTR?
> **Answer:** Mean MTTR is heavily skewed by extreme outliers (e.g. an incident left open for months). Continuous percentiles (P50 median, P95) reflect true operational response times. Using SQL's native `PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (resolved_at - created_at)))` lets the database interpolate the 95th percentile value directly inside the query planner.

### Q12: Why did you use a GIN index on `tsvector` instead of `LIKE '%keyword%'`?
> **Answer:** A `LIKE '%keyword%'` query forces a sequential scan across all rows because leading wildcards cannot use B-tree indexes. On our 100,000-row synthetic benchmark, unindexed scans took **173.03 ms**. A Generalized Inverted Index (GIN) on a `tsvector` column breaks text into lexemes and maps each lexeme directly to row pointers, reducing query execution time to **36.60 ms** (a **4.73x speedup**).

### 13. Query Optimization: What is a partial index and where is it used?
> **Answer:** A partial index only indexes rows matching a `WHERE` predicate. On the `incidents` table, 95% of rows are historically resolved or closed. We created:
> ```sql
> CREATE INDEX ix_incidents_open_per_service
> ON incidents (service_id)
> WHERE status IN ('DETECTED', 'TRIGGERED', 'ACKNOWLEDGED', 'INVESTIGATING', 'MITIGATING');
> ```
> This keeps the index small in memory, speeds up live dashboard queries, and avoids scanning historical data.

### 14. Background Workers: How do Celery tasks execute async SQLAlchemy queries safely?
> **Answer:** Celery worker threads run synchronously. Creating or sharing an async event loop or session across worker calls causes deadlocks and connection leaks. We wrap each async task body in an isolated `asyncio.run(_async_task_body())` with a clean `async with SessionLocal() as session:` block. This guarantees a dedicated event loop and connection checkout per task invocation.

### 15. Security & Compliance: How do you guarantee secrets never leak into logs or source control?
> **Answer:** We enforce a defense-in-depth approach:
> 1. Hardcoded secrets were purged, and `.env` is ignored by Git. `.env.example` contains only sanitized placeholders.
> 2. Missing critical variables (`DATABASE_URL`, `JWT_SECRET`) cause the application to fail fast on startup with clear error messages.
> 3. An automated redaction pipeline (`redact_text` / `redact_mapping`) scrubs passwords, bearer tokens, private keys, and authorization headers from log messages and metadata before they are stored in PostgreSQL.
