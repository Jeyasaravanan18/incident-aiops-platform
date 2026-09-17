from uuid import uuid4

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hashing_and_verification() -> None:
    raw_pass = "ProductionSecurePassword123!"
    hashed = hash_password(raw_pass)

    assert hashed != raw_pass
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_access_token_lifecycle() -> None:
    user_id = uuid4()
    token = create_access_token(user_id, "ENGINEER")

    claims = decode_token(token, expected_type="access")
    assert claims["sub"] == str(user_id)
    assert claims["role"] == "ENGINEER"
    assert claims["type"] == "access"


def test_refresh_token_lifecycle() -> None:
    user_id = uuid4()
    token_id = uuid4()
    refresh_token = create_refresh_token(user_id, token_id)

    claims = decode_token(refresh_token, expected_type="refresh")
    assert claims["sub"] == str(user_id)
    assert claims["jti"] == str(token_id)
    assert claims["type"] == "refresh"


def test_token_type_mismatch_rejected() -> None:
    user_id = uuid4()
    access_token = create_access_token(user_id, "ADMIN")

    # Expecting refresh token but got access token
    with pytest.raises(ValueError, match="Invalid token type"):
        decode_token(access_token, expected_type="refresh")


def test_tampered_token_rejected() -> None:
    user_id = uuid4()
    token = create_access_token(user_id, "VIEWER")
    tampered = token[:-4] + "abcd"

    with pytest.raises(ValueError, match="Invalid token"):
        decode_token(tampered)
