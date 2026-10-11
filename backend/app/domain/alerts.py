"""Alert domain logic including server-side deterministic fingerprinting."""

import hashlib
import json
from uuid import UUID


def compute_alert_fingerprint(
    service_id: UUID,
    title: str,
    metadata_json: dict | None = None,
) -> str:
    """Compute server-side SHA-256 alert fingerprint for deduplication.

    Normalizes service_id, alert title, and severity-independent labels
    sorted by key, ensuring identical symptoms collapse to the exact same fingerprint.
    """
    labels: dict[str, str] = {}
    if metadata_json:
        # Exclude dynamic/transient telemetry metrics so duplicates collapse
        ignore_keys = {
            "severity",
            "timestamp",
            "time",
            "date",
            "created_at",
            "latency_ms",
            "response_time_ms",
            "occurrence_count",
            "id",
        }
        for k, v in metadata_json.items():
            k_clean = str(k).strip().lower()
            if k_clean not in ignore_keys and v is not None:
                labels[k_clean] = str(v).strip().lower()

    normalized_title = " ".join(title.strip().lower().split())
    normalized_service = str(service_id).strip().lower()
    canonical_labels = json.dumps(labels, sort_keys=True, separators=(",", ":"))

    payload = f"{normalized_service}:{normalized_title}:{canonical_labels}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
