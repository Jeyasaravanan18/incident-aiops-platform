# Architecture Decision Records (ADRs) & Engineering Trade-Offs

This document captures the architectural decisions, trade-offs, and technical rationale underpinning the **Production Incident Management & AIOps Platform**. It is specifically structured to equip engineering candidates to defend every design choice during technical interviews.

---

## 1. Modular Monolith vs. Distributed Microservices

### Context & Problem Statement
An incident response platform must orchestrate multiple capabilities: authentication, alert ingestion, stateful incident lifecycle transitions, service catalogs, structured log analysis, background health monitoring, real-time WebSocket notifications, and AI analysis.
The architectural dilemma is whether to split these into independent microservices (e.g. `auth-service`, `incident-service`, `alert-service`, `ai-service`) or structure them as a cohesive modular monolith.

### Alternatives Considered
1. **Microservices with gRPC / HTTP Mesh**: Each domain runs as a separate container with its own database.
2. **Serverless Functions (AWS Lambda / Cloud Run)**: Event-driven serverless handlers for alerts and background jobs.
3. **Modular Monolith**: Single deployable FastAPI application structured into strict domain modules (`app/domain`, `app/api`, `app/models`, `app/workers`).

### Decision & Technical Rationale
We selected the **Modular Monolith**.
- **Distributed Transactions & Consistency**: In an incident management system, an alert creation must atomically correlate with an active incident, record an immutable timeline audit event, and update service health. In a microservices architecture, this requires Distributed Sagas or Two-Phase Commits across network boundaries, introducing partial failure modes and distributed latency during the very outages the system is trying to mitigate.
- **Operational Complexity**: Microservices introduce distributed tracing overhead, network serialization tax, independent deployment pipelines, and cross-service schema synchronization. A modular monolith provides local transactional integrity, immediate in-memory domain calls, and zero network hops between submodules.
- **Clear Extraction Boundaries**: By enforcing clean separation of concerns—where APIs never directly manipulate foreign database tables and instead invoke domain functions—any submodule can be factored out into an independent service in the future if organizational scaling demands it.

### Trade-offs & Mitigations
- *Trade-off*: Monolithic deployment means all components share CPU/memory resources.
- *Mitigation*: Resource-heavy operations (e.g., periodic health checks, AI LLM context queries) are decoupled from the HTTP request-response cycle and offloaded to Celery distributed worker processes via Redis message brokers.

---

## 2. PostgreSQL + SQLAlchemy 2.0 Async vs. NoSQL / Document Store

### Context & Problem Statement
Incident management data includes structured tabular data (users, permissions, services, incidents, status enums) and unstructured semi-structured payloads (alert metadata, log payloads, AI evidence, timeline metadata).

### Alternatives Considered
1. **MongoDB / DocumentDB**: Flexible JSON document schemas for alerts and incident objects.
2. **PostgreSQL 16 with JSONB & Full-Text Search**: ACID relational database with native binary JSON and GIN index capabilities.
3. **Hybrid PostgreSQL + Elasticsearch**: PostgreSQL for core entities, Elasticsearch for logs and search.

### Decision & Technical Rationale
We selected **PostgreSQL 16 with SQLAlchemy 2.0 (asyncpg)**.
- **ACID Invariants & Foreign Key Integrity**: Incident lifecycles require strict relational integrity (e.g., an `IncidentAssignment` must refer to a valid `User` and `Incident`; deleting or altering records must maintain referential constraints).
- **JSONB for Semi-Structured Telemetry**: PostgreSQL's `JSONB` data type allows arbitrary metric and alert metadata payloads to be stored, indexed with GIN (Generalized Inverted Index), and queried with operators like `@>` and `->>` without abandoning relational integrity.
- **Single Source of Truth**: Introducing Elasticsearch would introduce eventual consistency lags and data synchronization pipelines, adding failure modes during critical production incidents.

---

## 3. Concurrency Control, Deduplication & Race Condition Defense

### Context & Problem Statement
During a major production outage (e.g. network partition or database crash), hundreds of monitoring agents and synthetic probes fire identical or related alerts simultaneously. Without strict concurrency control:
1. Multiple identical alerts could declare multiple duplicate SEV1 incidents for the same underlying failure.
2. Multiple responders acknowledging or updating an incident at the exact same millisecond could create conflicting timeline events.

### Decision & Implementation
- **Unique Fingerprint Constraints**: Every alert is computed with an upstream fingerprint:
  $$\text{fingerprint} = \text{SHA-256}(\text{source} \parallel \text{service\_slug} \parallel \text{check\_name})$$
  A unique constraint on `(fingerprint, status)` ensures that simultaneous alerts for the same underlying symptom map to a single database row.
- **Database-Level Atomic Upserts**: When an alert arrives, an atomic query matches on fingerprint: if an open alert exists, the database increments `occurrence_count` and updates `last_seen`.
- **Idempotency Keys**: Critical endpoints (alert ingestion, incident declaration) accept an `Idempotency-Key` header. The request hash is stored in Redis/PostgreSQL. Replaying the exact same request within a time window returns the cached HTTP response with zero duplicate processing.
- **State Machine Guardrails**: The `IncidentStatus` state transition engine strictly enforces valid DAG progression (`DETECTED` $\to$ `TRIGGERED` $\to$ `ACKNOWLEDGED` $\to$ `INVESTIGATING` $\to$ `MITIGATING` $\to$ `RESOLVED` $\to$ `CLOSED`). Invalid or retroactive state jumps throw `409 Conflict`.

---

## 4. Deterministic Rule-Based Severity Engine vs. Blind AI Classification

### Context & Problem Statement
When an alert triggers, should an AI model evaluate the severity, or should deterministic business logic calculate it?

### Decision & Technical Rationale
We chose **Deterministic Multi-Factor Scoring** as the foundational layer, with AI acting strictly as an investigative assistant.
- **Predictability & Explainability**: In high-stakes SRE environments, severity determines automated escalation policies (paging VP of Engineering, waking on-call engineers at 3 AM). An LLM's non-deterministic hallucination or rate limit failure must never prevent or distort emergency escalation.
- **Mathematical Scoring Formula**:
  $$\text{Score} = \text{Weight}(\text{AlertSeverity}) + \text{Weight}(\text{ServiceCriticality}) + \text{Bonus}(\text{BlastRadius}) + \text{Bonus}(\text{ErrorRate})$$
  - Score $\ge 7 \implies \text{SEV1}$ (Critical outage)
  - Score $\ge 5 \implies \text{SEV2}$ (Major degradation)
  - Score $\ge 3 \implies \text{SEV3}$ (Minor issue)
  - Otherwise $\implies \text{SEV4}$ (Low priority)

---

## 5. Decoupled AI/RAG Provider Strategy (Heuristic vs. OpenAI)

### Context & Problem Statement
Production incident triage requires synthesizing alerts, service metadata, historical postmortems, and contextual logs. However, relying solely on external cloud LLMs (OpenAI, Anthropic) introduces latency, privacy/compliance concerns (leaking internal customer data), cost, and internet dependency during corporate network isolations.

### Decision & Technical Rationale
We designed a clean **`LLMProvider` Protocol**:
```python
class LLMProvider(Protocol):
    async def analyze(self, context: dict[str, Any]) -> AIAnalysisResult: ...
    async def draft_postmortem(self, context: dict[str, Any]) -> PostmortemDraftResult: ...
```
1. **`HeuristicContextualProvider` (Local / Zero-Dependency)**:
   - Evaluates real context: cross-references active alerts, filters service logs, scans runbook steps for matching failure signatures, and extracts evidence.
   - Strictly separates **Observed Facts** from **Probable Hypotheses**.
   - Runs deterministically with zero API keys and zero cost—perfect for offline development, integration tests, and air-gapped deployments.
2. **`OpenAILLMProvider` (Production Cloud Mode)**:
   - Ingests the aggregated context and invokes GPT-4o / GPT-3.5-Turbo with JSON schema enforcement to produce rich investigative summaries when an API key is configured.

---

## 6. Celery + Redis for Background Processing vs. In-Process BackgroundTasks

### Context & Problem Statement
FastAPI provides lightweight `BackgroundTasks`. Why introduce the operational footprint of Celery and Redis?

### Decision & Technical Rationale
- **Process Isolation & Crash Resilience**: If an in-process `BackgroundTask` encounters an unhandled segmentation fault, out-of-memory error, or infinite loop during log analysis or health probing, it can crash the main HTTP server process serving critical incident responders.
- **Horizontal Scalability**: Celery workers can be scaled independently on dedicated compute nodes without scaling the web tier.
- **Scheduled & Periodic Execution (Celery Beat)**: Periodic synthetic health checks (every 30s) and health history cleanups require persistent distributed scheduling that survives application restarts.
- **Exponential Backoff & Retries**: Celery provides battle-tested retry policies with exponential jitter for flaky network calls when probing downstream services.
