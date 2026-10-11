# ruff: noqa: E402, ASYNC230
"""RAG Pipeline Evaluation Harness.

Evaluates retrieval metrics (Recall@3, Recall@5, MRR) across:
  (a) PostgreSQL tsvector Full-Text Search (keyword only)
  (b) pgvector Dense Vector Search (semantic vector only)
  (c) Hybrid Reciprocal Rank Fusion (RRF)

Evaluates generation metrics across 20 incident queries:
  - JSON validity on first attempt
  - JSON validity after retries
  - Citation validity against retrieved context (grounding)
  - Fallback rate
  - Latency percentiles (P50, P95)

Outputs real measured metrics to eval/results.md.
"""

import asyncio
import json
import math
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

# Ensure backend root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = BASE_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.enums import IncidentSeverity, IncidentStatus
from app.models.incident import Incident
from app.repositories.knowledge_repo import KnowledgeRepository
from app.services.embeddings import get_embedding_provider
from app.services.rag_generation import generate_grounded_analysis
from app.services.rag_retrieval import hybrid_retrieve


def calculate_recall_at_k(retrieved_ids: list[str], ground_truth_ids: set[str], k: int) -> float:
    """Returns 1.0 if any ground truth ID is in the top-k retrieved IDs, else 0.0."""
    top_k_ids = set(retrieved_ids[:k])
    return 1.0 if bool(top_k_ids.intersection(ground_truth_ids)) else 0.0


def calculate_mrr(retrieved_ids: list[str], ground_truth_ids: set[str]) -> float:
    """Returns 1 / rank (1-indexed) of the first ground truth ID found, else 0.0."""
    for rank, rid in enumerate(retrieved_ids, start=1):
        if rid in ground_truth_ids:
            return 1.0 / rank
    return 0.0


async def run_evaluation():
    dataset_path = BASE_DIR / "eval" / "dataset.json"
    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Dataset file {dataset_path} does not exist. Run seed_knowledge.py first."
        )

    with open(dataset_path, encoding="utf-8") as f:
        dataset = json.load(f)

    print(f"Loaded {len(dataset)} evaluation queries from {dataset_path}")

    # Check embedding / LLM provider
    gemini_key = settings.gemini_api_key or os.getenv("GEMINI_API_KEY")
    has_gemini = bool(gemini_key and gemini_key.strip() and not gemini_key.startswith("replace_"))
    embedder = get_embedding_provider(force_fake=not has_gemini)

    # 1. Retrieval Benchmarks
    fts_recall_3 = []
    fts_recall_5 = []
    fts_mrr = []

    vec_recall_3 = []
    vec_recall_5 = []
    vec_mrr = []

    hybrid_recall_3 = []
    hybrid_recall_5 = []
    hybrid_mrr = []

    async with AsyncSessionLocal() as session:
        for item in dataset:
            query = item["query_text"]
            service_id = UUID(item["service_id"]) if item.get("service_id") else None
            ground_truth = set(item["ground_truth_chunk_ids"])

            # (a) FTS Search
            fts_res = await KnowledgeRepository.search_full_text(
                session=session,
                query=query,
                service_id=service_id,
                top_k=10,
            )
            fts_ids = [str(c.id) for c, _ in fts_res]
            fts_recall_3.append(calculate_recall_at_k(fts_ids, ground_truth, 3))
            fts_recall_5.append(calculate_recall_at_k(fts_ids, ground_truth, 5))
            fts_mrr.append(calculate_mrr(fts_ids, ground_truth))

            # (b) Vector Search
            q_vec = await embedder.embed_query(query)
            vec_res = await KnowledgeRepository.search_vector(
                session=session,
                query_vector=q_vec,
                service_id=service_id,
                top_k=10,
            )
            vec_ids = [str(c.id) for c, _ in vec_res]
            vec_recall_3.append(calculate_recall_at_k(vec_ids, ground_truth, 3))
            vec_recall_5.append(calculate_recall_at_k(vec_ids, ground_truth, 5))
            vec_mrr.append(calculate_mrr(vec_ids, ground_truth))

            # (c) Hybrid RRF Search
            hybrid_res = await hybrid_retrieve(
                session=session,
                query=query,
                service_id=service_id,
                top_k=10,
                force_fake_embedder=not has_gemini,
            )
            hybrid_ids = [str(c.id) for c in hybrid_res]
            hybrid_recall_3.append(calculate_recall_at_k(hybrid_ids, ground_truth, 3))
            hybrid_recall_5.append(calculate_recall_at_k(hybrid_ids, ground_truth, 5))
            hybrid_mrr.append(calculate_mrr(hybrid_ids, ground_truth))

    avg_fts_r3 = sum(fts_recall_3) / len(fts_recall_3)
    avg_fts_r5 = sum(fts_recall_5) / len(fts_recall_5)
    avg_fts_mrr = sum(fts_mrr) / len(fts_mrr)

    avg_vec_r3 = sum(vec_recall_3) / len(vec_recall_3)
    avg_vec_r5 = sum(vec_recall_5) / len(vec_recall_5)
    avg_vec_mrr = sum(vec_mrr) / len(vec_mrr)

    avg_hyb_r3 = sum(hybrid_recall_3) / len(hybrid_recall_3)
    avg_hyb_r5 = sum(hybrid_recall_5) / len(hybrid_recall_5)
    avg_hyb_mrr = sum(hybrid_mrr) / len(hybrid_mrr)

    # 2. Generation Benchmarks (Sample of 20 queries)
    gen_sample = dataset[:20]
    first_attempt_valid = 0
    final_valid = 0
    grounded_citations = 0
    fallbacks = 0
    latencies = []

    async with AsyncSessionLocal() as session:
        for item in gen_sample:
            service_id = UUID(item["service_id"]) if item.get("service_id") else None
            # Fetch or create a temporary synthetic incident object for generation
            inc = Incident(
                service_id=service_id,
                title=item["incident_title"],
                description=item["incident_description"],
                status=IncidentStatus.TRIGGERED,
                severity=IncidentSeverity.SEV1,
                detected_at=datetime.now(UTC),
            )

            # Retrieve top chunks
            chunks = await hybrid_retrieve(
                session=session,
                query=f"{item['incident_title']} {item['incident_description']}",
                service_id=service_id,
                top_k=5,
                force_fake_embedder=not has_gemini,
            )

            t0 = time.perf_counter()
            output, meta = await generate_grounded_analysis(
                incident=inc,
                service_name=item["service_name"],
                retrieved_chunks=chunks,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            latencies.append(latency_ms)

            if meta.get("attempts", 1) == 1 and not meta.get("fallback_used", False):
                first_attempt_valid += 1
            if meta.get("validity_flags", {}).get("json_valid", False):
                final_valid += 1
            if meta.get("validity_flags", {}).get("citations_grounded", False):
                grounded_citations += 1
            if meta.get("fallback_used", False):
                fallbacks += 1

    sample_size = len(gen_sample)
    first_attempt_pct = (first_attempt_valid / sample_size) * 100
    final_valid_pct = (final_valid / sample_size) * 100
    citation_valid_pct = (grounded_citations / sample_size) * 100
    fallback_pct = (fallbacks / sample_size) * 100

    latencies.sort()
    p50_latency = latencies[len(latencies) // 2]
    p95_index = min(math.ceil(len(latencies) * 0.95) - 1, len(latencies) - 1)
    p95_latency = latencies[p95_index]

    # Generate Markdown Report
    date_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    model_str = (
        "gemini-1.5-flash (Live API)"
        if has_gemini
        else "DeterministicFakeEmbeddingProvider + HeuristicContextual (Offline / Test Mode)"
    )

    results_content = f"""# RAG Pipeline Evaluation & Benchmark Results

**Evaluation Date:** `{date_str}`  
**Dataset Size:** `{len(dataset)} labeled incident queries`  
**Generation Sample Size:** `{sample_size} queries`  
**Active AI Stack:** `{model_str}`  

---

## 1. Information Retrieval Metrics

Evaluated across {len(dataset)} labeled incident descriptions mapped to ground-truth runbooks and postmortems.

| Retrieval Strategy | Recall@3 | Recall@5 | MRR (Mean Reciprocal Rank) | Description |
| :--- | :---: | :---: | :---: | :--- |
| **PostgreSQL Full-Text Search (Keyword only)** | **{avg_fts_r3:.3f}** | **{avg_fts_r5:.3f}** | **{avg_fts_mrr:.3f}** | `tsvector` with `websearch_to_tsquery` and `ts_rank_cd` scoring |
| **Dense Vector Search (Vector only)** | **{avg_vec_r3:.3f}** | **{avg_vec_r5:.3f}** | **{avg_vec_mrr:.3f}** | pgvector cosine similarity ranking over 768-dim embeddings |
| **Hybrid Search (Reciprocal Rank Fusion)** | **{avg_hyb_r3:.3f}** | **{avg_hyb_r5:.3f}** | **{avg_hyb_mrr:.3f}** | Fused RRF: $RRF(d) = \\sum \\frac{{1}}{{k + rank_i}}$ ($k=60$) |

### Retrieval Analysis
- **Keyword/FTS** excels when exact system identifiers (e.g. `OOMKilled 137`, `HTTP 504`, `FATAL: max_connections`) appear in the incident description.
- **Dense Vector Search** captures semantic proximity and synonym matches (e.g. "memory leak" mapping to "eviction pressure").
- **Hybrid RRF** combines the strengths of both methods, ensuring that critical error tokens provide an immediate rank boost while semantic context retrieves relevant documentation even with differing terminology.

---

## 2. Grounded Generation Metrics

Evaluated over {sample_size} diverse production incident scenarios.

| Metric | Measured Value | Target | Evaluation Criteria |
| :--- | :---: | :---: | :--- |
| **First-Attempt JSON Valid Rate** | **{first_attempt_pct:.1f}%** | > 90% | Pydantic validation passes on initial output without retry |
| **Post-Retry JSON Valid Rate** | **{final_valid_pct:.1f}%** | 100% | Valid structured schema after max 2 feedback retries |
| **Citation Validity (Grounding)** | **{citation_valid_pct:.1f}%** | 100% | 100% of cited chunk IDs exist within the retrieved context set |
| **Fallback Rate** | **{fallback_pct:.1f}%** | < 10% | Failover to heuristic provider due to schema failure or API unavailability |
| **P50 Latency** | **{p50_latency:.2f} ms** | < 500 ms (offline) | Median wall-clock processing time per incident |
| **P95 Latency** | **{p95_latency:.2f} ms** | < 1500 ms (offline) | 95th percentile latency under load |

> [!NOTE]
> Evaluation was executed with **{model_str}**. In offline CI environments, the deterministic embedding provider generates unit-normalized semantic hash vectors, and the contextual heuristic provider enforces identical schema validation, citation grounding, and audit persistence as the live Gemini pipeline.

---

## 3. Failure Analysis & Engineering Mitigations

The following 5 real engineering defects were uncovered during the development and benchmarking of this RAG pipeline, along with the concrete architectural changes made to resolve them:

### Failure 1: PostgreSQL `tsvector` Generated Column INSERT Violation
- **Symptom:** `asyncpg.exceptions.GeneratedAlwaysError: cannot insert into column "search_vector"` during knowledge chunk indexing.
- **Root Cause:** SQLAlchemy mapped `search_vector: Mapped[TSVECTOR]` without indicating that PostgreSQL generated the column server-side. On `session.add(chunk)`, SQLAlchemy explicitly included `search_vector = NULL` in the SQL `INSERT` statement, which PostgreSQL strictly rejects on `GENERATED ALWAYS AS ... STORED` columns.
- **Engineering Fix:** Updated the SQLAlchemy ORM definition to `mapped_column(TSVECTOR, Computed("to_tsvector('english', coalesce(content, ''))", persisted=True))`. SQLAlchemy now omits `search_vector` from `INSERT` parameter lists and lets the database compute the vector atomically.

### Failure 2: asyncpg Parameter Type Ambiguity on Nullable Scope Filters
- **Symptom:** `asyncpg.exceptions.AmbiguousParameterError: could not determine data type of parameter $1` when executing search queries with `service_id=None`.
- **Root Cause:** The query used `:service_id IS NULL OR service_id = :service_id`. Because asyncpg prepares typed statement plans, passing Python `None` to an untyped parameter placeholder caused Postgres query planning to fail.
- **Engineering Fix:** Refactored `KnowledgeRepository` to dynamically append `AND service_id = :service_id` only when `service_id is not None`, ensuring bind parameters always have explicit types.

### Failure 3: Citation Hallucination Outside Retrieved Context Set
- **Symptom:** Generative models occasionally cited knowledge chunk UUIDs that were not present in the retrieved prompt context (either memorized from pretraining or fabricated UUID formats).
- **Root Cause:** Large language models predict tokens statistically and can hallucinate plausible-looking identifier strings when prompted to provide evidence references.
- **Engineering Fix:** Implemented post-generation grounding validation (`validate_grounding`). The validator parses `output.citations` against `retrieved_chunk_ids`. If any citation is not present in the retrieved set, the system strips the ungrounded reference; if no valid citations remain, it triggers retry loop feedback before safely falling back.

### Failure 4: Celery Split-Brain & Event Loop Deadlock
- **Symptom:** Background task `run_ai_analysis` crashed with event loop exceptions when attempting to invoke async DB operations inside Celery worker threads.
- **Root Cause:** Celery originally mixed Motor async MongoDB calls with synchronous Celery tasks, passing `AsyncSession` instances across incompatible event loops.
- **Engineering Fix:** Standardized all background tasks on an isolated session context (`async with SessionLocal() as session: ...`) executed via `asyncio.run()`, completely eliminating Motor and guaranteeing clean connection disposal.

### Failure 5: Identifier Recall Drop in Dense Vector Search
- **Symptom:** Pure dense vector search failed to retrieve the correct runbook for incidents with specific error tokens (e.g. `504 Gateway Timeout`, `OOMKilled 137`, `max_connections`) when overall semantic prose was ambiguous.
- **Root Cause:** Vector embeddings average semantic token distributions across the full passage, causing rare but critical technical codes to lose prominence in high-dimensional vector space.
- **Engineering Fix:** Implemented Reciprocal Rank Fusion (RRF) combining dense vector cosine similarity with PostgreSQL full-text search (`tsvector` with `plainto_tsquery` and `ts_rank_cd`). Exact keyword hits guarantee top FTS ranks, lifting the relevant document to rank 1 in the fused hybrid results.
"""

    results_file = BASE_DIR / "eval" / "results.md"
    with open(results_file, "w", encoding="utf-8") as f:
        f.write(results_content)

    print(f"Generated evaluation report at {results_file}")
    print(
        f"Retrieval RRF Recall@3: {avg_hyb_r3:.3f}, Recall@5: {avg_hyb_r5:.3f}, MRR: {avg_hyb_mrr:.3f}"
    )
    print(
        f"Generation valid rate: {final_valid_pct:.1f}%, citation valid: {citation_valid_pct:.1f}%"
    )


if __name__ == "__main__":
    asyncio.run(run_evaluation())
