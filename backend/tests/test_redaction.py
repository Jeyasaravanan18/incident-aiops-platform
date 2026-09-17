from app.domain.redaction import redact_mapping, redact_text


def test_redacts_secrets_from_log_message() -> None:
    value = redact_text("database password=supersecret token=abc123")
    assert "supersecret" not in value
    assert "abc123" not in value
    assert "[REDACTED]" in value


def test_redacts_nested_metadata() -> None:
    value = redact_mapping({"safe": "ok", "nested": {"authorization": "Bearer abc"}})
    assert value["safe"] == "ok"
    assert value["nested"]["authorization"] == "[REDACTED]"
