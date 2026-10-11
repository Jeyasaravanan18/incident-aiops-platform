"""RAG Generation engine with strict Pydantic JSON validation, retry loop, and citation grounding checks.

Enforces:
1. Structured generation matching GroundedRAGOutput.
2. Citation grounding validation: all cited chunk UUIDs must exist in the retrieved set.
3. Up to 2 retries on malformed JSON or validation errors, feeding back the error trace.
4. Resilient fallback to HeuristicContextualProvider with fallback_used=True on persistent failure.
5. Audit metric tracking (latency, attempts, validity flags, chunk scores).
"""

import json
import logging
import re
import time
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from app.ai.provider import HeuristicContextualProvider, get_llm_provider
from app.models.incident import Incident
from app.services.rag_retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

PROMPT_VERSION = "rag-v1.0"


class GroundedRAGOutput(BaseModel):
    summary: str
    likely_causes: list[str] = Field(min_length=1)
    recommended_actions: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[UUID] = Field(default_factory=list)


def build_rag_prompt(
    incident: Incident,
    service_name: str,
    retrieved_chunks: list[RetrievedChunk],
    validation_error: str | None = None,
) -> str:
    """Constructs prompt containing incident symptoms and retrieved knowledge chunks with grounding instructions."""
    chunks_text = "\n\n".join(
        f"--- KNOWLEDGE CHUNK [id={c.id}] (Source: {c.source_type}) ---\n{c.content}"
        for c in retrieved_chunks
    )

    prompt = (
        "You are a Principal Site Reliability Engineer conducting root-cause analysis for a live incident.\n\n"
        f"INCIDENT DETAILS:\n"
        f"- Title: {incident.title}\n"
        f"- Service: {service_name}\n"
        f"- Severity: {incident.severity.value if hasattr(incident.severity, 'value') else incident.severity}\n"
        f"- Description: {incident.description or 'N/A'}\n\n"
        f"RETRIEVED HISTORICAL KNOWLEDGE:\n"
        f"{chunks_text if chunks_text else 'No historical runbooks or postmortems found.'}\n\n"
        "TASK:\n"
        "Synthesize the likely root causes and recommended remediation actions.\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. Every citation in 'citations' MUST be an exact chunk UUID from the KNOWLEDGE CHUNK headers above.\n"
        "2. Do NOT invent, hallucinate, or cite any ID that is not listed above.\n"
        "3. If no chunks are relevant, leave 'citations' empty [].\n"
        "4. Respond with a single valid JSON object strictly matching this schema:\n"
        "{\n"
        '  "summary": "High-level summary of the incident and operational blast radius",\n'
        '  "likely_causes": ["Cause 1", "Cause 2"],\n'
        '  "recommended_actions": ["Action 1", "Action 2"],\n'
        '  "confidence": 0.85,\n'
        '  "citations": ["<uuid-1>", "<uuid-2>"]\n'
        "}\n"
    )

    if validation_error:
        prompt += (
            f"\n\nPREVIOUS ATTEMPT FAILED WITH VALIDATION ERROR:\n{validation_error}\n"
            "Please fix the error, strictly ensure valid JSON, and only use valid chunk UUIDs in 'citations'."
        )

    return prompt


def _extract_json_block(text: str) -> str:
    """Extracts JSON substring if wrapped in markdown code fences."""
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text.strip()


async def generate_grounded_analysis(
    incident: Incident,
    service_name: str,
    retrieved_chunks: list[RetrievedChunk],
    max_retries: int = 2,
) -> tuple[GroundedRAGOutput, dict]:
    """Generates grounded incident analysis with retry and fallback.

    Returns:
        (GroundedRAGOutput, audit_metadata_dict)
    """
    start_time = time.perf_counter()
    retrieved_chunk_ids = {c.id for c in retrieved_chunks}
    llm_provider = get_llm_provider()

    model_name = (
        getattr(llm_provider, "model", "gemini-1.5-flash")
        if hasattr(llm_provider, "api_key")
        else "heuristic-v1"
    )

    # If already using the heuristic provider (no external API key)
    if isinstance(llm_provider, HeuristicContextualProvider):
        output = _build_heuristic_fallback(incident, service_name, retrieved_chunks)
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        metadata = {
            "model_name": "heuristic-contextual",
            "prompt_version": PROMPT_VERSION,
            "retrieved_chunk_ids": [str(c.id) for c in retrieved_chunks],
            "chunk_scores": {str(c.id): c.rrf_score for c in retrieved_chunks},
            "latency_ms": latency_ms,
            "attempts": 1,
            "validity_flags": {"json_valid": True, "citations_grounded": True},
            "fallback_used": True,
        }
        return output, metadata

    attempts = 0
    last_error: str | None = None

    while attempts <= max_retries:
        attempts += 1
        prompt = build_rag_prompt(
            incident=incident,
            service_name=service_name,
            retrieved_chunks=retrieved_chunks,
            validation_error=last_error,
        )

        try:
            raw_response = await llm_provider.generate(prompt)
            clean_json = _extract_json_block(raw_response)
            parsed = json.loads(clean_json)
            output = GroundedRAGOutput.model_validate(parsed)

            # Grounding check: verify that all citations are in retrieved_chunk_ids
            hallucinations = [cid for cid in output.citations if cid not in retrieved_chunk_ids]
            if hallucinations:
                raise ValueError(
                    f"Hallucinated citations not in retrieved set: {[str(h) for h in hallucinations]}"
                )

            latency_ms = int((time.perf_counter() - start_time) * 1000)
            metadata = {
                "model_name": model_name,
                "prompt_version": PROMPT_VERSION,
                "retrieved_chunk_ids": [str(c.id) for c in retrieved_chunks],
                "chunk_scores": {str(c.id): c.rrf_score for c in retrieved_chunks},
                "latency_ms": latency_ms,
                "attempts": attempts,
                "validity_flags": {"json_valid": True, "citations_grounded": True},
                "fallback_used": False,
            }
            return output, metadata

        except (json.JSONDecodeError, ValidationError, ValueError, Exception) as exc:
            last_error = f"{type(exc).__name__}: {str(exc)}"
            logger.warning("RAG generation attempt %d failed: %s", attempts, last_error)

    # All attempts exhausted: fallback to heuristic provider
    output = _build_heuristic_fallback(incident, service_name, retrieved_chunks)
    latency_ms = int((time.perf_counter() - start_time) * 1000)
    metadata = {
        "model_name": model_name,
        "prompt_version": PROMPT_VERSION,
        "retrieved_chunk_ids": [str(c.id) for c in retrieved_chunks],
        "chunk_scores": {str(c.id): c.rrf_score for c in retrieved_chunks},
        "latency_ms": latency_ms,
        "attempts": attempts,
        "validity_flags": {
            "json_valid": False,
            "citations_grounded": True,
            "last_error": last_error,
        },
        "fallback_used": True,
    }
    return output, metadata


def _build_heuristic_fallback(
    incident: Incident,
    service_name: str,
    retrieved_chunks: list[RetrievedChunk],
) -> GroundedRAGOutput:
    """Builds a grounded, deterministic fallback analysis citing the top retrieved chunks."""
    top_citations = [c.id for c in retrieved_chunks[:2]]
    title = incident.title
    return GroundedRAGOutput(
        summary=f"Automated incident analysis for {service_name}: {title}. Degraded operational state observed.",
        likely_causes=[
            f"Service degradation in {service_name} correlating with alert triggers: {title}",
            "Upstream dependency latency spikes or connection pool saturation",
        ],
        recommended_actions=[
            "Inspect recent deployment diffs and service health metric dashboards",
            "Verify database connection pool thresholds and restart degraded replicas if necessary",
            "Execute standard mitigation procedure from referenced runbooks",
        ],
        confidence=0.75 if top_citations else 0.50,
        citations=top_citations,
    )
