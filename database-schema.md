# Database Schema

## Entity Relationships

```text
User
 ├── RefreshToken
 ├── IncidentAssignment
 ├── IncidentComment
 ├── TimelineEvent
 └── AuditLog

Service
 ├── Alert
 ├── Incident
 ├── ServiceHealthCheck
 ├── LogEntry
 └── Runbook

Incident
 ├── Alert
 ├── IncidentAssignment
 ├── TimelineEvent
 ├── IncidentComment
 ├── AIAnalysis
 └── Postmortem
```

## Constraints

- UUID primary keys for public identifiers.
- Unique `users.email`.
- Unique `services.slug`.
- Unique active alert fingerprint scope through `alerts.fingerprint`.
- Check constraints for enum-like fields where useful.
- Foreign keys preserve ownership and timeline integrity.

## Important Indexes

- `incidents(status)`: active incident queues filter by status.
- `incidents(severity)`: dashboard and escalation views group by severity.
- `incidents(service_id)`: service detail pages load related incidents.
- `incidents(created_at)`: analytics over time windows.
- `alerts(fingerprint)`: deduplication path must be fast and concurrency-safe.
- `alerts(status)`: alert inbox filtering.
- `alerts(service_id)`: service alert history.
- `log_entries(service_id, timestamp)`: recent service logs around an incident.
- `log_entries(level, timestamp)`: error-focused investigations.
- `timeline_events(incident_id, created_at)`: incident detail timeline.
- `audit_logs(actor_id, created_at)`: compliance review.

Indexes are intentionally scoped to query paths rather than every column.

## Retention

Raw service health checks are retained for a configurable short window. Aggregates can be kept longer for analytics. Logs should be retained according to environment policy and should be redacted before storage.

## Performance Notes

Important queries should be inspected with `EXPLAIN` or `EXPLAIN ANALYZE`:

- active incidents by severity and service
- alert fingerprint lookup during ingestion
- recent error logs by service and time range
- MTTA/MTTR analytics over selected period

