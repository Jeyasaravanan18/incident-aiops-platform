from app.domain.idempotency import payload_hash


def test_payload_hash_is_stable_for_key_order() -> None:
    left = payload_hash({"service_id": "a", "metadata": {"b": 1, "a": 2}})
    right = payload_hash({"metadata": {"a": 2, "b": 1}, "service_id": "a"})

    assert left == right


def test_payload_hash_changes_when_payload_changes() -> None:
    assert payload_hash({"fingerprint": "one"}) != payload_hash({"fingerprint": "two"})
