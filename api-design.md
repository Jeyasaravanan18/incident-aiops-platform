# API Design

All application APIs are versioned under `/api/v1`.

## Error Format

```json
{
  "error": {
    "code": "INCIDENT_NOT_FOUND",
    "message": "Incident not found",
    "request_id": "..."
  }
}
```

## Auth

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/password-reset/request`

## Services

- `GET /api/v1/services`
- `POST /api/v1/services`
- `GET /api/v1/services/{service_id}`
- `PATCH /api/v1/services/{service_id}`
- `DELETE /api/v1/services/{service_id}`
- `GET /api/v1/services/{service_id}/health`

## Alerts

- `POST /api/v1/alerts`
- `GET /api/v1/alerts`
- `POST /api/v1/alerts/{alert_id}/acknowledge`
- `POST /api/v1/alerts/{alert_id}/resolve`
- `POST /api/v1/alerts/{alert_id}/suppress`

Ingestion accepts `Idempotency-Key`.

## Incidents

- `GET /api/v1/incidents`
- `POST /api/v1/incidents`
- `GET /api/v1/incidents/{incident_id}`
- `POST /api/v1/incidents/{incident_id}/transition`
- `POST /api/v1/incidents/{incident_id}/assign`
- `POST /api/v1/incidents/{incident_id}/comments`
- `GET /api/v1/incidents/{incident_id}/timeline`

## Logs

- `POST /api/v1/logs`
- `GET /api/v1/logs`

Log ingestion redacts obvious secrets before persistence.

## Runbooks, Postmortems, Analytics, AI

- `GET /api/v1/runbooks`
- `POST /api/v1/runbooks`
- `POST /api/v1/postmortems`
- `GET /api/v1/analytics/summary`
- `POST /api/v1/ai/incidents/{incident_id}/analysis`

## WebSockets

- `/ws/incidents/{incident_id}`
- `/ws/services/{service_id}`
- `/ws/dashboard`

