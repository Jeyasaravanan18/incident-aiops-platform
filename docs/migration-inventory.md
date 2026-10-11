# MongoDB Migration Inventory

This inventory documents every usage of `motor`, `pymongo`, `AsyncIOMotorDatabase`, `AsyncIOMotorClient`, and `db.` collection operations across the codebase prior to the single-database PostgreSQL migration.

---

## 1. Overview of MongoDB Touchpoints

| File Path | Component Type | Collections / Operations | Primary Affected Endpoints / Functions |
|---|---|---|---|
| `backend/app/core/database.py` | Database Engine & Client | Client pooling, index creation, doc normalization | `get_mongo_client`, `get_database`, `get_db`, `init_db_indexes`, `clean_doc`, `clean_docs` |
| `backend/app/core/config.py` | Configuration Settings | MongoDB Atlas connection string | `mongodb_url`, `mongodb_db_name` |
| `backend/app/main.py` | FastAPI Application Lifespan | Client lifecycle & `/ready` probe | `lifespan` (index init + client close), `/ready` endpoint ping |
| `backend/app/api/deps.py` | Security & Auth Dependencies | `users` | `current_user` auth lookup |
| `backend/app/domain/idempotency.py` | Idempotency Engine | `idempotency_records` | `get_idempotent_response`, `store_idempotent_response` |
| `backend/app/scripts/seed.py` | Data Seeding Script | `users`, `services`, `incidents`, `alerts`, `logs`, `runbooks`, `timeline_events`, `comments`, `postmortems` | `seed_database` async CLI runner |
| `backend/app/api/v1/auth.py` | Authentication Router | `users`, `refresh_tokens` | `POST /register`, `POST /login`, `POST /refresh`, `POST /logout` |
| `backend/app/api/v1/users.py` | User Management Router | `users` | `GET /users/me`, `GET /users` |
| `backend/app/api/v1/services.py` | Service Catalog Router | `services`, `incidents`, `health_checks` | `GET /services`, `POST /services`, `GET /services/{id}`, `PATCH /services/{id}`, `DELETE /services/{id}`, `GET /services/{id}/health`, `POST /services/{id}/health-check` |
| `backend/app/api/v1/alerts.py` | Alert Ingestion Router | `alerts`, `services`, `incidents`, `timeline_events`, `idempotency_records` | `GET /alerts`, `POST /alerts`, `GET /alerts/{id}`, `POST /alerts/{id}/acknowledge`, `POST /alerts/{id}/suppress`, `POST /alerts/{id}/resolve` |
| `backend/app/api/v1/incidents.py` | Incident Management Router | `incidents`, `services`, `users`, `alerts`, `timeline_events`, `incident_assignments`, `incident_comments` | `GET /incidents`, `POST /incidents`, `GET /incidents/{id}`, `PATCH /incidents/{id}`, `POST /incidents/{id}/transition`, `POST /incidents/{id}/reopen`, `POST /incidents/{id}/assign`, `POST /incidents/{id}/comments`, `GET /incidents/{id}/comments`, `GET /incidents/{id}/timeline`, `GET /incidents/{id}/alerts` |
| `backend/app/api/v1/logs.py` | Structured Logs Router | `logs`, `services` | `POST /logs`, `GET /logs` |
| `backend/app/api/v1/runbooks.py` | Runbook Knowledge Router | `runbooks`, `services` | `GET /runbooks`, `POST /runbooks`, `GET /runbooks/{id}`, `PATCH /runbooks/{id}`, `DELETE /runbooks/{id}` |
| `backend/app/api/v1/postmortems.py` | Postmortem Library Router | `postmortems`, `incidents`, `users` | `GET /postmortems`, `POST /postmortems`, `GET /postmortems/{id}`, `GET /postmortems/by-incident/{id}`, `PATCH /postmortems/{id}` |
| `backend/app/api/v1/ai.py` | AIOps & Root Cause Router | `incidents`, `services`, `alerts`, `logs`, `runbooks`, `ai_analyses`, `timeline_events` | `POST /ai/incidents/{id}/analysis`, `GET /ai/incidents/{id}/analysis`, `POST /ai/incidents/{id}/postmortem-draft`, `POST /ai/incidents/{id}/remediation`, `collect_incident_context` |
| `backend/app/api/v1/analytics.py` | SRE Reliability Metrics | `incidents`, `alerts`, `services`, `health_checks` | `GET /analytics/summary` |
| `backend/app/api/v1/notifications.py` | Alert Notifications Router | `notifications` | `GET /notifications`, `POST /notifications/{id}/read` |

---

## 2. Granular Endpoint-by-Endpoint Inventory

### 2.1 Auth (`backend/app/api/v1/auth.py`)
- `POST /api/v1/auth/register`:
  - `db.users.find_one({"email": ...})`
  - `db.users.insert_one(user_doc)`
  - `db.refresh_tokens.insert_one(...)`
- `POST /api/v1/auth/login`:
  - `db.users.find_one({"email": ...})`
  - `db.refresh_tokens.insert_one(...)`
- `POST /api/v1/auth/refresh`:
  - `db.refresh_tokens.find_one({"id": ...})`
  - `db.refresh_tokens.update_one({"id": ...}, {"$set": {"revoked_at": ...}})`
  - `db.users.find_one({"id": ...})`
  - `db.refresh_tokens.insert_one(...)`
- `POST /api/v1/auth/logout`:
  - `db.refresh_tokens.update_one({"id": ...}, {"$set": {"revoked_at": ...}})`

### 2.2 Users (`backend/app/api/v1/users.py`)
- `GET /api/v1/users/me`:
  - `db.users.find_one({"id": user.id})`
- `GET /api/v1/users`:
  - `db.users.find({"is_active": True})`

### 2.3 Services (`backend/app/api/v1/services.py`)
- `GET /api/v1/services`:
  - `db.services.find()`
  - `db.incidents.find({"status": {"$in": ...}})`
  - `db.health_checks.find(...)` per service
- `POST /api/v1/services`:
  - `db.services.find_one({"slug": ...})`
  - `db.services.insert_one(doc)`
- `GET /api/v1/services/{service_id}`:
  - `db.services.find_one({"id": ...})`
  - `db.health_checks.find({"service_id": ...})`
- `PATCH /api/v1/services/{service_id}`:
  - `db.services.find_one({"id": ...})`
  - `db.services.update_one({"id": ...}, {"$set": ...})`
- `DELETE /api/v1/services/{service_id}`:
  - `db.services.delete_one({"id": ...})`
- `GET /api/v1/services/{service_id}/health`:
  - `db.services.find_one({"id": ...})`
  - `db.health_checks.find({"service_id": ...})`
- `POST /api/v1/services/{service_id}/health-check`:
  - `db.services.find_one({"id": ...})`
  - `db.health_checks.insert_one(check_doc)`
  - `db.services.update_one({"id": ...}, {"$set": {"status": ...}})`

### 2.4 Alerts (`backend/app/api/v1/alerts.py`)
- `GET /api/v1/alerts`:
  - `db.alerts.find(query)`
  - `db.services.find({"id": {"$in": service_ids}})`
- `POST /api/v1/alerts`:
  - `db.services.find_one({"id": ...})`
  - `db.alerts.find_one({"fingerprint": ...})` (deduplication check)
  - `db.alerts.update_one(...)` on deduplication
  - `db.incidents.find_one(...)` for active correlation
  - `db.alerts.insert_one(...)`
  - `db.incidents.update_one(...)` for severity adjustment
  - `db.timeline_events.insert_one(...)`
- `GET /api/v1/alerts/{alert_id}`:
  - `db.alerts.find_one({"id": ...})`
- `POST /api/v1/alerts/{alert_id}/acknowledge`:
  - `db.alerts.find_one({"id": ...})`
  - `db.alerts.update_one({"id": ...}, {"$set": ...})`
- `POST /api/v1/alerts/{alert_id}/suppress`:
  - `db.alerts.find_one({"id": ...})`
  - `db.alerts.update_one({"id": ...}, {"$set": ...})`
- `POST /api/v1/alerts/{alert_id}/resolve`:
  - `db.alerts.find_one({"id": ...})`
  - `db.alerts.update_one({"id": ...}, {"$set": ...})`

### 2.5 Incidents (`backend/app/api/v1/incidents.py`)
- `GET /api/v1/incidents`:
  - `db.incidents.find(query)`
  - `db.services.find(...)`, `db.users.find(...)`, `db.alerts.count_documents(...)`
- `POST /api/v1/incidents`:
  - `db.services.find_one({"id": ...})`
  - `db.incidents.insert_one(...)`
  - `db.timeline_events.insert_one(...)`
- `GET /api/v1/incidents/{incident_id}`:
  - `db.incidents.find_one({"id": ...})`
  - `db.services.find_one(...)`, `db.users.find_one(...)`
  - `db.timeline_events.find(...)`, `db.alerts.find(...)`, `db.incident_comments.find(...)`
- `PATCH /api/v1/incidents/{incident_id}`:
  - `db.incidents.find_one({"id": ...})`
  - `db.incidents.update_one(...)`
- `POST /api/v1/incidents/{incident_id}/transition`:
  - `db.incidents.find_one({"id": ...})`
  - `db.incidents.update_one(...)`
  - `db.timeline_events.insert_one(...)`
- `POST /api/v1/incidents/{incident_id}/reopen`:
  - `db.incidents.find_one({"id": ...})`
  - `db.incidents.update_one(...)`
  - `db.timeline_events.insert_one(...)`
- `POST /api/v1/incidents/{incident_id}/assign`:
  - `db.incidents.find_one({"id": ...})`
  - `db.users.find_one({"id": assignee_id})`
  - `db.incidents.update_one(...)`
  - `db.incident_assignments.insert_one(...)`
  - `db.timeline_events.insert_one(...)`
- `POST /api/v1/incidents/{incident_id}/comments`:
  - `db.incidents.find_one({"id": ...})`
  - `db.incident_comments.insert_one(...)`
- `GET /api/v1/incidents/{incident_id}/comments`:
  - `db.incidents.find_one({"id": ...})`
  - `db.incident_comments.find({"incident_id": ...})`
  - `db.users.find(...)`
- `GET /api/v1/incidents/{incident_id}/timeline`:
  - `db.timeline_events.find({"incident_id": ...})`
  - `db.users.find(...)`
- `GET /api/v1/incidents/{incident_id}/alerts`:
  - `db.alerts.find({"incident_id": ...})`

### 2.6 Logs (`backend/app/api/v1/logs.py`)
- `POST /api/v1/logs`:
  - `db.services.find_one(...)`
  - `db.logs.insert_one(entry)`
- `GET /api/v1/logs`:
  - `db.logs.find(query)`

### 2.7 Runbooks (`backend/app/api/v1/runbooks.py`)
- `GET /api/v1/runbooks`:
  - `db.runbooks.find(query)`
  - `db.services.find(...)`
- `POST /api/v1/runbooks`:
  - `db.services.find_one(...)`
  - `db.runbooks.insert_one(...)`
- `GET /api/v1/runbooks/{runbook_id}`:
  - `db.runbooks.find_one({"id": ...})`
- `PATCH /api/v1/runbooks/{runbook_id}`:
  - `db.runbooks.find_one({"id": ...})`
  - `db.runbooks.update_one(...)`
- `DELETE /api/v1/runbooks/{runbook_id}`:
  - `db.runbooks.delete_one({"id": ...})`

### 2.8 Postmortems (`backend/app/api/v1/postmortems.py`)
- `GET /api/v1/postmortems`:
  - `db.postmortems.find()`
  - `db.incidents.find(...)`, `db.users.find(...)`
- `POST /api/v1/postmortems`:
  - `db.incidents.find_one({"id": ...})`
  - `db.postmortems.find_one({"incident_id": ...})`
  - `db.postmortems.insert_one(...)`
  - `db.timeline_events.insert_one(...)`
- `GET /api/v1/postmortems/{postmortem_id}`:
  - `db.postmortems.find_one({"id": ...})`
- `GET /api/v1/postmortems/by-incident/{incident_id}`:
  - `db.postmortems.find_one({"incident_id": ...})`
- `PATCH /api/v1/postmortems/{postmortem_id}`:
  - `db.postmortems.find_one({"id": ...})`
  - `db.postmortems.update_one(...)`

### 2.9 AI / AIOps (`backend/app/api/v1/ai.py`)
- Context collector (`collect_incident_context`):
  - `db.services.find_one({"id": ...})`
  - `db.alerts.find({"incident_id": ...})`
  - `db.logs.find(...)`
  - `db.runbooks.find(...)`
  - `db.incidents.find(...)` (historical resolved)
- `POST /api/v1/ai/incidents/{incident_id}/analysis`:
  - `db.incidents.find_one({"id": ...})`
  - `db.ai_analyses.insert_one(...)`
  - `db.timeline_events.insert_one(...)`
- `GET /api/v1/ai/incidents/{incident_id}/analysis`:
  - `db.ai_analyses.find_one({"incident_id": ...})`
- `POST /api/v1/ai/incidents/{incident_id}/postmortem-draft`:
  - `db.incidents.find_one({"id": ...})`
- `POST /api/v1/ai/incidents/{incident_id}/remediation`:
  - `db.incidents.find_one({"id": ...})`

### 2.10 Analytics (`backend/app/api/v1/analytics.py`)
- `GET /api/v1/analytics/summary`:
  - `db.incidents.find({"created_at": {"$gte": cutoff}})`
  - `db.alerts.count_documents(...)`
  - `db.services.find()`
  - `db.health_checks.find(...)` per service

### 2.11 Notifications (`backend/app/api/v1/notifications.py`)
- `GET /api/v1/notifications`:
  - `db.notifications.find(...)`
- `POST /api/v1/notifications/{notification_id}/read`:
  - `db.notifications.find_one({"id": ...})`
  - `db.notifications.update_one(...)`

### 2.12 Infrastructure & Dependencies
- `backend/app/api/deps.py`:
  - `db.users.find_one({"id": ...})`
- `backend/app/domain/idempotency.py`:
  - `db.idempotency_records.find_one(...)`
  - `db.idempotency_records.insert_one(...)`
- `backend/app/core/database.py`:
  - `init_db_indexes()` creating indexes on users, services, incidents, alerts, timeline_events, postmortems, runbooks, notifications, idempotency_records.
- `backend/app/main.py`:
  - `lifespan`: `init_db_indexes()`, `client.close()`
  - `/ready`: `await db.command("ping")`

---

## 3. Migration Target Strategy
In Phase 1, every operation above will be mapped directly to:
1. `AsyncSession` dependency via `get_session`.
2. Dedicated repository/service functions consuming typed SQLAlchemy models.
3. Removal of all `clean_doc` normalization hacks since SQLAlchemy returns strongly-typed ORM objects.
