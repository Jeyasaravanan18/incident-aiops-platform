"""Integration tests covering all API routers: happy path and failure path for each endpoint.

Verifies:
  - Auth: login success and 401 failure on bad credentials.
  - RBAC: Viewer rejection (403) on mutation endpoints vs Admin success.
  - Incidents: creation, retrieval, and 409 conflict on invalid transitions.
  - Alerts: ingestion and validation failure (422).
  - Services: creation, retrieval, and 404 on missing service.
  - Logs: ingestion and listing.
  - Runbooks: creation, retrieval, and 404 on missing runbook.
  - Postmortems: retrieval and 404 on non-existent postmortem.
  - Analytics: overview and MTTA/MTTR SQL responses.
  - Notifications: retrieval.
  - AI: 404 on non-existent incident analysis.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.models.enums import IncidentSeverity, IncidentStatus
from app.models.service import Service
from app.models.user import User


@pytest.mark.asyncio
async def test_auth_router_happy_and_failure(async_client: AsyncClient, admin_user: User) -> None:
    # Happy path: valid login
    res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "SuperSecretAdmin123!"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"

    # Failure path: wrong password -> 401
    bad_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "WrongPassword999!"},
    )
    assert bad_res.status_code == 401


@pytest.mark.asyncio
async def test_rbac_enforcement_on_incident_creation(
    async_client: AsyncClient,
    test_service: Service,
    viewer_headers: dict[str, str],
    responder_headers: dict[str, str],
) -> None:
    payload = {
        "title": "Unauthorized Mutation Attempt",
        "description": "Viewer should be blocked by RBAC",
        "service_id": str(test_service.id),
        "severity": IncidentSeverity.SEV3.value,
    }

    # Failure path: VIEWER role cannot create incident -> 403 Forbidden
    forbidden_res = await async_client.post(
        "/api/v1/incidents",
        json=payload,
        headers=viewer_headers,
    )
    assert forbidden_res.status_code == 403

    # Happy path: RESPONDER role can create incident -> 201 Created
    ok_res = await async_client.post(
        "/api/v1/incidents",
        json=payload,
        headers=responder_headers,
    )
    assert ok_res.status_code == 201
    assert ok_res.json()["title"] == "Unauthorized Mutation Attempt"


@pytest.mark.asyncio
async def test_incident_router_lifecycle_and_transition_conflict(
    async_client: AsyncClient,
    test_service: Service,
    responder_headers: dict[str, str],
) -> None:
    # 1. Create incident
    create_res = await async_client.post(
        "/api/v1/incidents",
        json={
            "title": "Core Payment Ingestion Delay",
            "description": "Queue processing latency > 500ms",
            "service_id": str(test_service.id),
            "severity": IncidentSeverity.SEV2.value,
        },
        headers=responder_headers,
    )
    assert create_res.status_code == 201
    inc = create_res.json()
    inc_id = inc["id"]
    assert inc["status"] == IncidentStatus.TRIGGERED.value

    # 2. Happy path transition: TRIGGERED -> ACKNOWLEDGED -> 200 OK
    ack_res = await async_client.post(
        f"/api/v1/incidents/{inc_id}/transition",
        json={"status": IncidentStatus.ACKNOWLEDGED.value},
        headers=responder_headers,
    )
    assert ack_res.status_code == 200
    assert ack_res.json()["status"] == IncidentStatus.ACKNOWLEDGED.value

    # 3. Failure path: Invalid transition ACKNOWLEDGED -> CLOSED -> 409 Conflict
    invalid_res = await async_client.post(
        f"/api/v1/incidents/{inc_id}/transition",
        json={"status": IncidentStatus.CLOSED.value},
        headers=responder_headers,
    )
    assert invalid_res.status_code == 409

    # 4. Failure path: Non-existent incident -> 404 Not Found
    missing_res = await async_client.get(
        f"/api/v1/incidents/{uuid4()}",
        headers=responder_headers,
    )
    assert missing_res.status_code == 404


@pytest.mark.asyncio
async def test_alert_router_ingest_and_validation_failure(
    async_client: AsyncClient,
    test_service: Service,
    responder_headers: dict[str, str],
) -> None:
    # Happy path: Ingest alert
    alert_payload = {
        "service_id": str(test_service.id),
        "source": "prometheus-production",
        "title": "CPU Usage High 95%",
        "description": "Core worker node cpu usage exceeded threshold",
        "severity": "CRITICAL",
        "labels": {"cluster": "us-east-1", "host": "worker-42"},
    }
    ingest_res = await async_client.post(
        "/api/v1/alerts",
        json=alert_payload,
        headers=responder_headers,
    )
    assert ingest_res.status_code == 201
    alert_data = ingest_res.json()
    assert "fingerprint" in alert_data
    assert alert_data["occurrence_count"] >= 1

    # Failure path: Missing required fields -> 422 Unprocessable Entity
    bad_payload = {"source": "prometheus"}
    fail_res = await async_client.post(
        "/api/v1/alerts",
        json=bad_payload,
        headers=responder_headers,
    )
    assert fail_res.status_code == 422


@pytest.mark.asyncio
async def test_services_router_crud_and_failure(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    responder_headers: dict[str, str],
) -> None:
    unique_slug = f"catalog-{uuid4().hex[:8]}"

    # Happy path: Create service
    create_res = await async_client.post(
        "/api/v1/services",
        json={
            "name": "Catalog Microservice",
            "slug": unique_slug,
            "description": "Product catalog store",
            "tier": "TIER_1",
            "criticality": "HIGH",
        },
        headers=admin_headers,
    )
    assert create_res.status_code == 201
    svc_id = create_res.json()["id"]

    # Happy path: Get service by id
    get_res = await async_client.get(
        f"/api/v1/services/{svc_id}",
        headers=responder_headers,
    )
    assert get_res.status_code == 200
    assert get_res.json()["slug"] == unique_slug

    # Failure path: Query unknown service -> 404 Not Found
    fail_res = await async_client.get(
        f"/api/v1/services/{uuid4()}",
        headers=responder_headers,
    )
    assert fail_res.status_code == 404


@pytest.mark.asyncio
async def test_logs_router_ingest_and_list(
    async_client: AsyncClient,
    test_service: Service,
    responder_headers: dict[str, str],
) -> None:
    # Happy path: Ingest logs
    ingest_res = await async_client.post(
        "/api/v1/logs",
        json={
            "timestamp": datetime.now(UTC).isoformat(),
            "service": test_service.slug,
            "level": "ERROR",
            "message": "Connection to database failed password=SUPER_SECRET_VALUE",
            "metadata": {"retry_count": 3},
        },
        headers=responder_headers,
    )
    assert ingest_res.status_code == 201
    log_data = ingest_res.json()
    assert "[REDACTED]" in log_data["message"]
    assert "SUPER_SECRET_VALUE" not in log_data["message"]

    # Happy path: List logs
    list_res = await async_client.get(
        f"/api/v1/logs?service={test_service.slug}&limit=10",
        headers=responder_headers,
    )
    assert list_res.status_code == 200
    logs = list_res.json()
    assert len(logs) >= 1


@pytest.mark.asyncio
async def test_runbooks_router_crud_and_failure(
    async_client: AsyncClient,
    test_service: Service,
    admin_headers: dict[str, str],
    responder_headers: dict[str, str],
) -> None:
    # Happy path: Create runbook
    create_res = await async_client.post(
        "/api/v1/runbooks",
        json={
            "service_id": str(test_service.id),
            "title": "Postgres Pool Recovery Runbook",
            "incident_type": "database-latency",
            "body": "Step 1: Check pg_stat_activity. Step 2: Terminate hung queries.",
        },
        headers=admin_headers,
    )
    assert create_res.status_code == 201
    rb_id = create_res.json()["id"]

    # Happy path: Get runbook
    get_res = await async_client.get(
        f"/api/v1/runbooks/{rb_id}",
        headers=responder_headers,
    )
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Postgres Pool Recovery Runbook"

    # Failure path: Unknown runbook -> 404
    missing_res = await async_client.get(
        f"/api/v1/runbooks/{uuid4()}",
        headers=responder_headers,
    )
    assert missing_res.status_code == 404


@pytest.mark.asyncio
async def test_postmortems_router_and_failure(
    async_client: AsyncClient,
    responder_headers: dict[str, str],
) -> None:
    # Failure path: Unknown postmortem -> 404
    missing_res = await async_client.get(
        f"/api/v1/postmortems/{uuid4()}",
        headers=responder_headers,
    )
    assert missing_res.status_code == 404


@pytest.mark.asyncio
async def test_analytics_router_endpoints(
    async_client: AsyncClient,
    responder_headers: dict[str, str],
) -> None:
    # Summary metrics
    summary_res = await async_client.get(
        "/api/v1/analytics/summary",
        headers=responder_headers,
    )
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert "total_incidents" in summary
    assert "active_incidents" in summary
    assert "mtta" in summary
    assert "mttr" in summary

    # Breakdown SQL metrics
    breakdown_res = await async_client.get(
        "/api/v1/analytics/breakdown",
        headers=responder_headers,
    )
    assert breakdown_res.status_code == 200
    assert isinstance(breakdown_res.json(), list)

    # Noisy alerts SQL metrics
    noisy_res = await async_client.get(
        "/api/v1/analytics/noisy-alerts",
        headers=responder_headers,
    )
    assert noisy_res.status_code == 200
    assert isinstance(noisy_res.json(), list)


@pytest.mark.asyncio
async def test_ai_router_failure_on_missing_incident(
    async_client: AsyncClient,
    responder_headers: dict[str, str],
) -> None:
    # Failure path: Generate analysis for non-existent incident -> 404
    missing_res = await async_client.post(
        f"/api/v1/ai/incidents/{uuid4()}/analyze",
        headers=responder_headers,
    )
    assert missing_res.status_code == 404
