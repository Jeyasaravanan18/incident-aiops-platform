"""Hybrid search retrieval engine with Reciprocal Rank Fusion (RRF).

Combines dense vector semantic similarity with PostgreSQL tsvector full-text search,
merging rankings into a unified relevance order filtered by service scope.
"""

from collections import defaultdict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeChunk
from app.repositories.knowledge_repo import KnowledgeRepository
from app.services.embeddings import get_embedding_provider


class RetrievedChunk:
    def __init__(
        self,
        chunk: KnowledgeChunk,
        rrf_score: float,
        vector_rank: int | None = None,
        fts_rank: int | None = None,
        cosine_similarity: float | None = None,
    ):
        self.chunk = chunk
        self.id = chunk.id
        self.source_type = chunk.source_type
        self.source_id = chunk.source_id
        self.service_id = chunk.service_id
        self.content = chunk.content
        self.token_count = chunk.token_count
        self.rrf_score = rrf_score
        self.vector_rank = vector_rank
        self.fts_rank = fts_rank
        self.cosine_similarity = cosine_similarity

    def to_dict(self) -> dict:
        return {
            "chunk_id": str(self.id),
            "source_type": self.source_type,
            "source_id": str(self.source_id),
            "service_id": str(self.service_id) if self.service_id else None,
            "content": self.content,
            "token_count": self.token_count,
            "score": round(self.rrf_score, 6),
            "vector_rank": self.vector_rank,
            "fts_rank": self.fts_rank,
            "cosine_similarity": (
                round(self.cosine_similarity, 4) if self.cosine_similarity is not None else None
            ),
        }


async def hybrid_retrieve(
    session: AsyncSession,
    query: str,
    service_id: UUID | None = None,
    top_k: int = 5,
    rrf_k: int = 60,
    force_fake_embedder: bool = False,
) -> list[RetrievedChunk]:
    """Executes hybrid retrieval merging pgvector cosine search and PostgreSQL full-text search.

    Uses Reciprocal Rank Fusion (RRF):
        RRF_score(chunk) = sum_{system} 1 / (rrf_k + rank_{system})
    """
    embedder = get_embedding_provider(force_fake=force_fake_embedder)
    query_vector = await embedder.embed_query(query)

    # Fetch top candidates from both channels (over-fetch by 2x for fusion)
    fetch_limit = max(top_k * 2, 10)
    fts_results = await KnowledgeRepository.search_full_text(
        session=session,
        query=query,
        service_id=service_id,
        top_k=fetch_limit,
    )
    vec_results = await KnowledgeRepository.search_vector(
        session=session,
        query_vector=query_vector,
        service_id=service_id,
        top_k=fetch_limit,
    )

    rrf_scores: dict[UUID, float] = defaultdict(float)
    chunk_map: dict[UUID, KnowledgeChunk] = {}
    fts_ranks: dict[UUID, int] = {}
    vec_ranks: dict[UUID, int] = {}
    vec_sims: dict[UUID, float] = {}

    for rank, (chunk, _fts_score) in enumerate(fts_results, start=1):
        chunk_map[chunk.id] = chunk
        fts_ranks[chunk.id] = rank
        rrf_scores[chunk.id] += 1.0 / (rrf_k + rank)

    for rank, (chunk, sim) in enumerate(vec_results, start=1):
        chunk_map[chunk.id] = chunk
        vec_ranks[chunk.id] = rank
        vec_sims[chunk.id] = sim
        rrf_scores[chunk.id] += 1.0 / (rrf_k + rank)

    sorted_chunks = sorted(
        chunk_map.keys(),
        key=lambda cid: rrf_scores[cid],
        reverse=True,
    )

    results: list[RetrievedChunk] = []
    for cid in sorted_chunks[:top_k]:
        chunk = chunk_map[cid]
        results.append(
            RetrievedChunk(
                chunk=chunk,
                rrf_score=rrf_scores[cid],
                vector_rank=vec_ranks.get(cid),
                fts_rank=fts_ranks.get(cid),
                cosine_similarity=vec_sims.get(cid),
            )
        )

    return results
