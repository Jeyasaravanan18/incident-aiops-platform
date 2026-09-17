import re
from collections.abc import Mapping

SECRET_PATTERNS = [
    re.compile(r"(?i)(password|api[_-]?key|authorization|token)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)(bearer)\s+[a-z0-9._~+/=-]+"),
]


def redact_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
    return redacted


def redact_mapping(value: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in value.items():
        if key.lower() in {"password", "api_key", "apikey", "authorization", "token"}:
            result[key] = "[REDACTED]"
        elif isinstance(item, str):
            result[key] = redact_text(item)
        elif isinstance(item, Mapping):
            result[key] = redact_mapping(item)
        else:
            result[key] = item
    return result
