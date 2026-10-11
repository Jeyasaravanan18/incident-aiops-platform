"""API Contract Tests.

These tests capture and freeze the public HTTP API surface, endpoint paths,
required request schemas, and response shapes using httpx.AsyncClient.
Ensures that database refactoring across subsequent phases does not break
any frontend or consumer expectations.
"""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.main import app
from app.models.enums import Role
from app.schemas.alert import AlertRead
from app.schemas.analytics import AnalyticsSummaryResponse
from app.schemas.auth import TokenResponse
from app.schemas.incident import IncidentDetailRead, IncidentRead
from app.schemas.log import LogRead
from app.schemas.postmortem import PostmortemRead
from app.schemas.runbook import RunbookRead
from app.schemas.service import ServiceRead


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Generates a valid JWT bearer token header for an ADMIN engineer."""
    user_id = uuid4()
    token = create_access_token(user_id=user_id, role=Role.ADMIN.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_health_and_ready_contract() -> None:
    """Verifies operational health check endpoint contracts."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "ok"

        ready_resp = await client.get("/ready")
        assert ready_resp.status_code == 200
        ready_data = ready_resp.json()
        assert "status" in ready_data
        assert "database" in ready_data
        assert "redis" in ready_data


@pytest.mark.asyncio
async def test_openapi_schema_endpoint_coverage() -> None:
    """Verifies that all required REST endpoints are registered in the OpenAPI specification."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        paths = schema.get("paths", {})

        # Essential endpoint paths that must remain invariant
        expected_paths = [
            "/health",
            "/ready",
            "/metrics",
            "/api/v1/auth/register",
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/logout",
            "/api/v1/users/me",
            "/api/v1/users",
            "/api/v1/services",
            "/api/v1/services/{service_id}",
            "/api/v1/services/{service_id}/health",
            "/api/v1/services/{service_id}/health-check",
            "/api/v1/alerts",
            "/api/v1/alerts/{alert_id}",
            "/api/v1/alerts/{alert_id}/acknowledge",
            "/api/v1/alerts/{alert_id}/suppress",
            "/api/v1/alerts/{alert_id}/resolve",
            "/api/v1/incidents",
            "/api/v1/incidents/{incident_id}",
            "/api/v1/incidents/{incident_id}/transition",
            "/api/v1/incidents/{incident_id}/reopen",
            "/api/v1/incidents/{incident_id}/assign",
            "/api/v1/incidents/{incident_id}/comments",
            "/api/v1/incidents/{incident_id}/timeline",
            "/api/v1/incidents/{incident_id}/alerts",
            "/api/v1/logs",
            "/api/v1/runbooks",
            "/api/v1/runbooks/{runbook_id}",
            "/api/v1/postmortems",
            "/api/v1/postmortems/{postmortem_id}",
            "/api/v1/ai/incidents/{incident_id}/analysis",
            "/api/v1/ai/incidents/{incident_id}/postmortem-draft",
            "/api/v1/analytics/summary",
            "/api/v1/notifications",
        ]

        for expected in expected_paths:
            assert expected in paths, f"Missing expected contract route: {expected}"


@pytest.mark.asyncio
async def test_auth_protection_contract() -> None:
    """Verifies that protected routes reject unauthorized requests with 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Protected endpoints must reject missing bearer tokens
        assert (await client.get("/api/v1/users/me")).status_code == 401
        assert (await client.post("/api/v1/services", json={})).status_code == 401
        assert (await client.post("/api/v1/incidents", json={})).status_code == 401


@pytest.mark.asyncio
async def test_validation_error_contract() -> None:
    """Verifies that malformed payloads trigger 422 Unprocessable Entity."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Malformed login request
        resp = await client.post("/api/v1/auth/login", json={"invalid": "payload"})
        assert resp.status_code == 422


def test_schema_contracts() -> None:
    """Verifies that Core Pydantic response schemas contain all expected fields for consumers."""
    # TokenResponse
    token_fields = TokenResponse.model_fields.keys()
    assert {"access_token", "refresh_token", "token_type"}.issubset(token_fields)

    # ServiceRead
    service_fields = ServiceRead.model_fields.keys()
    assert {"id", "name", "slug", "environment", "status", "criticality"}.issubset(service_fields)

    # AlertRead
    alert_fields = AlertRead.model_fields.keys()
    assert {"id", "service_id", "source", "severity", "title", "fingerprint", "status"}.issubset(
        alert_fields
    )

    # IncidentRead
    incident_fields = IncidentRead.model_fields.keys()
    assert {"id", "service_id", "title", "status", "severity", "detected_at"}.issubset(
        incident_fields
    )

    # IncidentDetailRead
    detail_fields = IncidentDetailRead.model_fields.keys()
    assert {"timeline_events", "comments", "alert_count"}.issubset(detail_fields)

    # LogRead
    log_fields = LogRead.model_fields.keys()
    assert {"id", "timestamp", "service_name", "level", "message"}.issubset(log_fields)

    # RunbookRead
    runbook_fields = RunbookRead.model_fields.keys()
    assert {"id", "title", "incident_type", "body"}.issubset(runbook_fields)

    # PostmortemRead
    pm_fields = PostmortemRead.model_fields.keys()
    assert {"id", "incident_id", "summary", "impact", "timeline", "status"}.issubset(pm_fields)

    # AnalyticsSummaryResponse
    analytics_fields = AnalyticsSummaryResponse.model_fields.keys()
    assert {
        "total_incidents",
        "active_incidents",
        "resolved_incidents",
        "mtta",
        "mttr",
        "severity_breakdown",
    }.issubset(analytics_fields)
