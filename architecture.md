# Architecture

## Problem

Engineering teams need a reliable internal system that turns service signals into manageable incidents. The hard parts are not screens; they are consistency, deduplication, lifecycle control, authorization, observability, and safe AI assistance.

## Chosen Solution

The platform starts as a modular monolith:

- FastAPI API layer for REST and WebSockets
- PostgreSQL for persistent normalized state
- Redis for rate limiting, Celery broker/result backend, temporary coordination, and fan-out support
- Celery workers and Celery Beat for asynchronous and scheduled processing
- Next.js frontend for an operations dashboard
- LLM provider abstraction for replaceable AI analysis

This gives one deployable system with clear module boundaries that can later be extracted into services if scale requires it.

## Alternatives

- Microservices from day one: rejected because operational complexity would distract from correctness.
- Event streaming with Kafka: useful later, but Redis/Celery is sufficient for this project scope.
- Vector database immediately: postponed. PostgreSQL full-text search is enough for first RAG iteration and keeps local setup simple.

## Trade-Offs

The modular monolith keeps development and deployment approachable while still demonstrating serious backend design. The trade-off is that module boundaries require discipline because process isolation is not enforcing them.

## Bounded Domains

- Identity and access: users, roles, permissions, sessions, tokens
- Services and monitoring: service registry, health checks, health history
- Alerts: ingestion, deduplication, grouping, suppression, acknowledgement, resolution
- Incidents: lifecycle, severity, assignments, comments, timeline, audit
- Logs: structured ingestion, redaction, search, incident correlation
- AI/RAG: context collection, retrieval, provider abstraction, structured analysis
- Notifications: in-app and email architecture
- Analytics: MTTA, MTTR, severity distribution, service reliability

## Event Flow

```text
API command
  -> transaction
  -> domain state change
  -> timeline event
  -> audit log
  -> internal event
  -> websocket broadcast / notification / worker task
```

Events are durable where they represent timeline or audit facts. Transient delivery such as WebSocket fan-out is best effort.

## Celery Architecture

- `monitor_services`: scheduled by Celery Beat, checks registered health endpoints.
- `process_alert`: deduplicates and correlates alerts, creates or updates incidents.
- `run_ai_analysis`: collects incident context and stores structured analysis.
- `cleanup_health_history`: enforces retention.

Tasks are idempotent where duplicate delivery is possible and use retries with exponential backoff for external IO.

## AI Architecture

AI is isolated behind:

```python
class LLMProvider(Protocol):
    async def generate(self, prompt: str) -> str: ...
    async def summarize(self, context: str) -> str: ...
    async def analyze(self, context: Mapping[str, object]) -> IncidentAnalysisResult: ...
```

The application records AI output as suggestions with evidence labels:

- observed fact
- hypothesis
- recommendation

No AI response can execute production changes.

## Security Concerns

- JWT theft: short-lived access tokens and refresh token rotation.
- Privilege escalation: server-side RBAC checks on every sensitive route.
- Duplicate ingestion: idempotency keys and unique database constraints.
- Secret leakage: structured redaction before log storage.
- Prompt injection: retrieved context is treated as untrusted input and separated from system instructions.

## Concurrency Concerns

Duplicate alerts are controlled with a unique alert fingerprint plus transaction-level handling. Incident creation is coupled to alert grouping in a transaction so competing workers converge on the same incident.

