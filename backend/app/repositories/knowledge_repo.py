"""Repository for storing, re-embedding, and retrieving knowledge chunks."""

import math
import re
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.chunking import chunk_document
from app.models.knowledge import KnowledgeChunk
from app.services.embeddings import get_embedding_provider


def compute_cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Computes cosine similarity between two float vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return dot / (norm_a * norm_b)


class KnowledgeRepository:
    """Repository handling knowledge chunk indexing, vector persistence, and hybrid search."""

    @staticmethod
    async def index_document(
        session: AsyncSession,
        source_type: str,
        source_id: UUID,
        service_id: UUID | None,
        content: str,
    ) -> list[KnowledgeChunk]:
        """Chunks, embeds, and indexes a source document into knowledge_chunks.

        Replaces any existing chunks for this (source_type, source_id).
        """
        # Delete existing chunks for this source
        await session.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.source_type == source_type,
                KnowledgeChunk.source_id == source_id,
            )
        )

        passages = chunk_document(content)
        if not passages:
            return []

        embedder = get_embedding_provider()
        texts = [p["content"] for p in passages]
        embeddings = await embedder.embed_documents(texts)

        chunks: list[KnowledgeChunk] = []
        for passage, emb in zip(passages, embeddings, strict=True):
            chunk = KnowledgeChunk(
                id=uuid4(),
                source_type=source_type,
                source_id=source_id,
                service_id=service_id,
                content=passage["content"],
                token_count=passage["token_count"],
                embedding=emb,
            )
            session.add(chunk)
            chunks.append(chunk)

        await session.flush()
        return chunks

    @staticmethod
    async def search_full_text(
        session: AsyncSession,
        query: str,
        service_id: UUID | None = None,
        top_k: int = 10,
    ) -> list[tuple[KnowledgeChunk, float]]:
        words = re.findall(r"[A-Za-z0-9_-]+", query)
        terms = [w for w in words if len(w) >= 3][:15]
        fts_expr = " or ".join(terms) if terms else query

        where_clause = "search_vector @@ websearch_to_tsquery('english', :fts_query)"
        params: dict = {"fts_query": fts_expr, "top_k": top_k}
        if service_id is not None:
            where_clause += " AND service_id = :service_id"
            params["service_id"] = service_id

        sql = f"""
            SELECT id, ts_rank_cd(search_vector, websearch_to_tsquery('english', :fts_query)) AS rank
            FROM knowledge_chunks
            WHERE {where_clause}
            ORDER BY rank DESC
            LIMIT :top_k
        """
        rows = (await session.execute(text(sql), params)).fetchall()

        if not rows:
            return []

        chunk_ids = [r[0] for r in rows]
        ranks = {r[0]: float(r[1]) for r in rows}

        chunks_stmt = select(KnowledgeChunk).where(KnowledgeChunk.id.in_(chunk_ids))
        chunks = (await session.scalars(chunks_stmt)).all()

        # Preserve order of relevance rank
        results = [
            (c, ranks[c.id]) for c in sorted(chunks, key=lambda x: ranks[x.id], reverse=True)
        ]
        return results

    @staticmethod
    async def search_vector(
        session: AsyncSession,
        query_vector: list[float],
        service_id: UUID | None = None,
        top_k: int = 10,
    ) -> list[tuple[KnowledgeChunk, float]]:
        """Executes dense vector search comparing cosine similarity."""
        # Query candidates filtered by service_id if provided
        stmt = select(KnowledgeChunk)
        if service_id is not None:
            stmt = stmt.where(
                (KnowledgeChunk.service_id == service_id) | (KnowledgeChunk.service_id.is_(None))
            )

        chunks = list((await session.scalars(stmt)).all())
        if not chunks:
            return []

        scored = []
        for c in chunks:
            sim = compute_cosine_similarity(query_vector, c.embedding)
            scored.append((c, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
