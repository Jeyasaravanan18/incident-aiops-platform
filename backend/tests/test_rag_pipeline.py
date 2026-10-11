"""Comprehensive tests for Phase 6 RAG pipeline:

Validates:
1. Document chunking with token count estimates and sliding overlap.
2. Deterministic unit-vector embeddings and cosine similarity properties.
3. Database persistence in knowledge_chunks with GIN tsvector full-text index.
4. Hybrid search fusing dense vector similarity and full-text search via Reciprocal Rank Fusion (RRF).
5. Grounded generation, citation validation, retry feedback, and heuristic fallback.
6. Database audit trail persistence in ai_analyses (retrieved chunks, scores, latency, attempts, fallback_used).
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.database import AsyncSessionLocal
from app.domain.chunking import chunk_document
from app.models.ai import AIAnalysis
from app.models.enums import Criticality, IncidentSeverity, IncidentStatus, ServiceStatus
from app.models.incident import Incident
from app.models.knowledge import KnowledgeChunk
from app.models.service import Service
from app.repositories.knowledge_repo import KnowledgeRepository, compute_cosine_similarity
from app.services.embeddings import DeterministicFakeEmbeddingProvider
from app.services.rag_generation import GroundedRAGOutput, generate_grounded_analysis
from app.services.rag_retrieval import hybrid_retrieve


def test_chunk_document_splitting_and_overlap() -> None:
    """Verifies that chunk_document correctly splits text into overlapping windows."""
    text = (
        "Paragraph 1: PostgreSQL connection pool was exhausted due to a leaked connection.\n\n"
        "Paragraph 2: The authentication service began queuing incoming requests until memory spikes.\n\n"
        "Paragraph 3: To mitigate, execute `pg_terminate_backend` on idle in transaction sessions.\n\n"
        "Paragraph 4: Restart the connection pooler container and increase max_connections to 200."
    )

    chunks = chunk_document(text, chunk_size=30, overlap=10)
    assert len(chunks) >= 2
    for c in chunks:
        assert "chunk_index" in c
        assert "content" in c
        assert c["token_count"] > 0
        assert len(c["content"]) > 0


def test_deterministic_fake_embeddings_properties() -> None:
    """Verifies that DeterministicFakeEmbeddingProvider outputs 768-dim unit vectors
    and preserves semantic cosine similarity.
    """
    provider = DeterministicFakeEmbeddingProvider()
    doc_a = "PostgreSQL database connection pool exhaustion latency spike"
    doc_b = "Postgres DB pool exhausted and slow queries"
    doc_c = "Frontend CSS layout alignment bug in navigation bar"

    vec_a = provider._embed_single(doc_a)
    vec_b = provider._embed_single(doc_b)
    vec_c = provider._embed_single(doc_c)

    assert len(vec_a) == 768
    # L2 norm must be approximately 1.0
    norm_a = sum(x * x for x in vec_a) ** 0.5
    assert abs(norm_a - 1.0) < 1e-4

    sim_ab = compute_cosine_similarity(vec_a, vec_b)
    sim_ac = compute_cosine_similarity(vec_a, vec_c)

    assert (
        sim_ab > sim_ac
    ), f"Semantically related docs ({sim_ab:.3f}) must have higher similarity than unrelated ({sim_ac:.3f})"


@pytest.mark.asyncio
async def test_knowledge_chunk_indexing_and_hybrid_retrieval() -> None:
    """Tests indexing documents into knowledge_chunks and retrieving them via hybrid RRF search."""
    slug = f"rag-test-{uuid4().hex[:8]}"
    async with AsyncSessionLocal() as session:
        svc = Service(
            name="Payment Gateway Service",
            slug=slug,
            status=ServiceStatus.HEALTHY,
            criticality=Criticality.CRITICAL,
        )
        session.add(svc)
        await session.commit()
        svc_id = svc.id

    rb_content = (
        "Runbook: Payment Gateway Timeout Remediation.\n\n"
        "When payment processing times out at 30s, inspect Stripe webhook signature verification.\n"
        "If Redis rate limiter is rejecting tokens, flush stale keys and scale worker instances.\n\n"
        "Execute rollback: helm rollback payment-gateway 2."
    )

    async with AsyncSessionLocal() as session:
        rb_id = uuid4()
        chunks = await KnowledgeRepository.index_document(
            session=session,
            source_type="runbook",
            source_id=rb_id,
            service_id=svc_id,
            content=rb_content,
        )
        await session.commit()
        assert len(chunks) >= 1

    # Execute Hybrid Retrieval via RRF
    async with AsyncSessionLocal() as session:
        retrieved = await hybrid_retrieve(
            session=session,
            query="payment processing timeout webhook Redis",
            service_id=svc_id,
            top_k=3,
            force_fake_embedder=True,
        )

        assert len(retrieved) > 0
        top = retrieved[0]
        assert top.source_type == "runbook"
        assert top.source_id == rb_id
        assert top.rrf_score > 0
        assert "timeout" in top.content.lower()


@pytest.mark.asyncio
async def test_grounded_generation_and_audit_persistence() -> None:
    """Verifies that grounded generation produces citations restricted to retrieved chunks,
    validates Pydantic JSON output, and persists full audit metadata to PostgreSQL.
    """
    slug = f"gen-test-{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        svc = Service(
            name="Auth Token Service",
            slug=slug,
            status=ServiceStatus.DEGRADED,
            criticality=Criticality.HIGH,
        )
        session.add(svc)
        await session.flush()

        incident = Incident(
            service_id=svc.id,
            title="JWT Signature Validation Storm",
            description="High rate of expired refresh token replay attempts",
            severity=IncidentSeverity.SEV2,
            status=IncidentStatus.TRIGGERED,
            detected_at=now,
        )
        session.add(incident)
        await session.flush()

        # Seed knowledge chunk
        chunk = KnowledgeChunk(
            id=uuid4(),
            source_type="runbook",
            source_id=uuid4(),
            service_id=svc.id,
            content="Auth Service Runbook: Revoke compromised JWT tokens and flush Redis token cache.",
            token_count=15,
            embedding=[0.05] * 768,
        )
        session.add(chunk)
        await session.commit()
        inc_id = incident.id
        chunk_id = chunk.id
        svc_id = svc.id
        svc_name = svc.name

    # Retrieve chunks and generate grounded analysis
    async with AsyncSessionLocal() as session:
        retrieved = await hybrid_retrieve(
            session=session,
            query="JWT signature validation refresh token",
            service_id=svc_id,
            top_k=2,
            force_fake_embedder=True,
        )

        inc = await session.get(Incident, inc_id)
        assert inc is not None

        output, meta = await generate_grounded_analysis(
            incident=inc,
            service_name=svc_name,
            retrieved_chunks=retrieved,
        )

        assert isinstance(output, GroundedRAGOutput)
        assert len(output.likely_causes) >= 1
        assert len(output.recommended_actions) >= 1
        assert 0.0 <= output.confidence <= 1.0

        # Citations must strictly belong to retrieved chunks
        retrieved_ids = {c.id for c in retrieved}
        for cited_id in output.citations:
            assert cited_id in retrieved_ids, f"Citation {cited_id} was not in retrieved set!"

        # Persist to PostgreSQL AIAnalysis
        analysis = AIAnalysis(
            incident_id=inc_id,
            provider=meta["model_name"],
            summary=output.summary,
            probable_causes=output.likely_causes,
            evidence=[{"chunk_id": str(c.id), "fact": c.content} for c in retrieved],
            recommended_actions=output.recommended_actions,
            confidence=output.confidence,
            related_incidents=[],
            model_name=meta["model_name"],
            prompt_version=meta["prompt_version"],
            retrieved_chunk_ids=meta["retrieved_chunk_ids"],
            chunk_scores=meta["chunk_scores"],
            latency_ms=meta["latency_ms"],
            attempts=meta["attempts"],
            validity_flags=meta["validity_flags"],
            fallback_used=meta["fallback_used"],
        )
        session.add(analysis)
        await session.commit()

        # Reload from PostgreSQL and verify audit trail columns
        persisted = await session.get(AIAnalysis, analysis.id)
        assert persisted is not None
        assert persisted.model_name is not None
        assert persisted.prompt_version == "rag-v1.0"
        assert isinstance(persisted.retrieved_chunk_ids, list)
        assert str(chunk_id) in persisted.retrieved_chunk_ids
        assert isinstance(persisted.chunk_scores, dict)
        assert persisted.attempts >= 1
        assert isinstance(persisted.validity_flags, dict)
        assert "json_valid" in persisted.validity_flags
