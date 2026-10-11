"""Text chunker for the RAG ingestion pipeline.

Chunks markdown documents, postmortems, and runbooks into semantically coherent
passages with sliding window overlap while tracking token estimates.
"""

import re


def estimate_tokens(text: str) -> int:
    """Estimates token count using standard word-to-token ratio (~1.3 tokens per whitespace word)."""
    words = len(text.strip().split())
    return max(1, int(words * 1.3))


def chunk_document(
    text: str,
    chunk_size: int = 400,
    overlap: int = 80,
) -> list[dict]:
    """Chunks text into passages preserving paragraph/section boundaries with overlap.

    Returns a list of dicts:
        [{"chunk_index": i, "content": "...", "token_count": int}, ...]
    """
    clean_text = text.strip()
    if not clean_text:
        return []

    # Split by markdown headers, section breaks, or double newlines
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", clean_text) if p.strip()]
    chunks: list[dict] = []
    current_passage: list[str] = []
    current_tokens = 0
    chunk_idx = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)

        # If a single paragraph exceeds chunk size, split it into sentences
        if para_tokens > chunk_size:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", para) if s.strip()]
            for sentence in sentences:
                s_tokens = estimate_tokens(sentence)
                if current_tokens + s_tokens > chunk_size and current_passage:
                    combined = " ".join(current_passage)
                    chunks.append(
                        {
                            "chunk_index": chunk_idx,
                            "content": combined,
                            "token_count": estimate_tokens(combined),
                        }
                    )
                    chunk_idx += 1
                    # Keep overlap from the end of current passage
                    overlap_words = " ".join(combined.split()[-overlap:])
                    current_passage = [overlap_words] if overlap_words else []
                    current_tokens = estimate_tokens(overlap_words)

                current_passage.append(sentence)
                current_tokens += s_tokens
            continue

        if current_tokens + para_tokens > chunk_size and current_passage:
            combined = "\n\n".join(current_passage)
            chunks.append(
                {
                    "chunk_index": chunk_idx,
                    "content": combined,
                    "token_count": estimate_tokens(combined),
                }
            )
            chunk_idx += 1
            overlap_words = " ".join(combined.split()[-overlap:])
            current_passage = [overlap_words] if overlap_words else []
            current_tokens = estimate_tokens(overlap_words)

        current_passage.append(para)
        current_tokens += para_tokens

    if current_passage:
        combined = "\n\n".join(current_passage)
        chunks.append(
            {
                "chunk_index": chunk_idx,
                "content": combined,
                "token_count": estimate_tokens(combined),
            }
        )

    return chunks
