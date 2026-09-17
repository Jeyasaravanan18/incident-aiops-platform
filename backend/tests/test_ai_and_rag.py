import pytest

from app.ai.provider import HeuristicContextualProvider, get_llm_provider


@pytest.mark.asyncio
async def test_heuristic_provider_analyzes_context() -> None:
    provider = HeuristicContextualProvider()
    context = {
        "title": "Payment API database connection pool exhausted",
        "service_name": "Payment API",
        "severity": "SEV1",
        "status": "TRIGGERED",
        "alerts": [
            {
                "title": "High 5xx Error Rate",
                "severity": "CRITICAL",
                "fingerprint": "pay-5xx-prod",
                "source": "prometheus",
            },
            {
                "title": "Database Pool Saturation",
                "severity": "CRITICAL",
                "fingerprint": "pay-pool-sat",
                "source": "datadog",
            },
        ],
        "logs": [
            {
                "level": "ERROR",
                "message": "Timeout acquiring connection from pool after 3000ms",
                "trace_id": "trace-101",
            },
            {
                "level": "CRITICAL",
                "message": "Connection pool saturation detected (98/100 active)",
                "trace_id": "trace-102",
            },
        ],
        "runbooks": [
            {
                "id": "rb-1",
                "title": "Payment Database Pool Triage",
                "body": "1. Check pg_stat_activity.\n2. Scale pool ceiling from 100 to 150.\n3. Escalate to DBA.",
            }
        ],
        "history": [{"id": "hist-1", "title": "Historical flash sale pool exhaustion"}],
    }

    result = await provider.analyze(context)

    # 1. Summary generated
    assert "Payment API" in result.summary
    assert result.confidence > 0.60

    # 2. Evidence extracted with kinds
    kinds = [e["kind"] for e in result.evidence]
    assert "alert" in kinds
    assert "log" in kinds
    assert "runbook" in kinds

    # 3. Hypotheses distinguished from facts
    for cause in result.probable_causes:
        assert cause.startswith("HYPOTHESIS")

    # 4. Recommended actions pulled from runbook
    assert len(result.recommended_actions) >= 3
    assert any("pg_stat_activity" in a for a in result.recommended_actions)

    # 5. Related historical incidents included
    assert len(result.related_incidents) >= 1


@pytest.mark.asyncio
async def test_postmortem_draft_generation() -> None:
    provider = HeuristicContextualProvider()
    context = {
        "title": "Inventory Redis cache stampede",
        "service_name": "Inventory Service",
        "detected_at": "2026-09-16T12:00:00Z",
        "resolved_at": "2026-09-16T12:35:00Z",
    }

    draft = await provider.draft_postmortem(context)
    assert "Inventory Service" in draft.summary
    assert draft.impact != ""
    assert draft.timeline != ""
    assert draft.root_cause != ""
    assert draft.resolution != ""
    assert "preventive_actions" in draft.model_dump()


def test_provider_factory() -> None:
    provider = get_llm_provider()
    assert provider is not None
    assert hasattr(provider, "analyze")
    assert hasattr(provider, "draft_postmortem")
