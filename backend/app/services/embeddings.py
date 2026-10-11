"""Embedding provider interface and implementations for RAG.

Includes:
1. `EmbeddingProvider` abstract interface.
2. `DeterministicFakeEmbeddingProvider` producing stable 768-dim unit-normalized
   embeddings for deterministic unit tests, CI, and offline benchmarks without external API keys.
3. `GeminiEmbeddingProvider` calling Google Gemini text-embedding-004 API when configured.
"""

import hashlib
import math
import os
import sys
from abc import ABC, abstractmethod

import httpx

from app.core.config import settings

VECTOR_DIMENSION = 768


class EmbeddingProvider(ABC):
    """Abstract interface for dense semantic embedding models."""

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Embeds a single query string into a dense vector."""
        ...

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embeds a batch of document texts into dense vectors."""
        ...


class DeterministicFakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic, bag-of-words hash projection embedding model.

    Generates stable 768-dimensional L2-normalized vectors using SHA-256 projections.
    Guarantees that semantically overlapping texts have higher cosine similarity
    than unrelated texts, enabling realistic hybrid search tests without external APIs.
    """

    def _hash_token(self, token: str) -> list[float]:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        # Derive pseudo-random float coordinates from byte values
        return [((b / 255.0) * 2.0 - 1.0) for b in digest]

    def _embed_single(self, text: str) -> list[float]:
        tokens = [t.lower() for t in text.split() if t.isalnum()]
        if not tokens:
            tokens = ["empty"]

        vec = [0.0] * VECTOR_DIMENSION
        step = len(hashlib.sha256(b"").digest())  # 32 bytes

        for token in tokens:
            seed_bytes = self._hash_token(token)
            for i in range(VECTOR_DIMENSION):
                # Distribute token seed cyclically with dimension-dependent harmonic phase
                harmonic = math.sin((i + 1) * 0.1)
                coord = seed_bytes[i % step] * harmonic
                vec[i] += coord

        # L2 unit normalization: v / ||v||
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 1e-9:
            return [x / norm for x in vec]
        return [1.0 / math.sqrt(VECTOR_DIMENSION)] * VECTOR_DIMENSION

    async def embed_query(self, text: str) -> list[float]:
        return self._embed_single(text)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_single(t) for t in texts]


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Google Gemini text-embedding-004 provider."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.endpoint = "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent"

    async def embed_query(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.endpoint}?key={self.api_key}",
                json={
                    "model": "models/text-embedding-004",
                    "content": {"parts": [{"text": text}]},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["embedding"]["values"]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            vec = await self.embed_query(text)
            results.append(vec)
        return results


def is_testing_environment() -> bool:
    return (
        os.getenv("TESTING", "").lower() in ("1", "true", "yes")
        or "pytest" in sys.modules
        or any("pytest" in arg for arg in sys.argv)
    )


def get_embedding_provider(force_fake: bool = False) -> EmbeddingProvider:
    """Returns GeminiEmbeddingProvider if API key is present and not testing; else DeterministicFakeEmbeddingProvider."""
    if (
        not force_fake
        and not is_testing_environment()
        and settings.gemini_api_key
        and not settings.gemini_api_key.startswith("test-")
    ):
        return GeminiEmbeddingProvider(api_key=settings.gemini_api_key)
    return DeterministicFakeEmbeddingProvider()
