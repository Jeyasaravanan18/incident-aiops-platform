from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    payload: RegisterRequest, db: AsyncIOMotorDatabase = Depends(get_db)
) -> TokenResponse:
    email_str = str(payload.email).lower()
    existing = await db.users.find_one({"email": email_str})
    if existing:
        raise AppError("EMAIL_ALREADY_REGISTERED", "Email already registered", 409)

    user_id = str(uuid4())
    now = datetime.now(UTC)
    user_doc = {
        "id": user_id,
        "email": email_str,
        "full_name": payload.full_name,
        "password_hash": hash_password(payload.password),
        "role": str(payload.role),
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(user_doc)

    refresh_id = str(uuid4())
    refresh = create_refresh_token(user_id, refresh_id)
    await db.refresh_tokens.insert_one(
        {
            "id": refresh_id,
            "user_id": user_id,
            "token_hash": hash_password(refresh),
            "expires_at": now + timedelta(days=settings.jwt_refresh_token_expire_days),
            "revoked_at": None,
            "created_at": now,
        }
    )
    return TokenResponse(
        access_token=create_access_token(user_id, str(payload.role)), refresh_token=refresh
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncIOMotorDatabase = Depends(get_db)) -> TokenResponse:
    email_str = str(payload.email).lower()
    user_doc = await db.users.find_one({"email": email_str})
    if user_doc is None or not verify_password(payload.password, user_doc.get("password_hash", "")):
        raise AppError("INVALID_CREDENTIALS", "Invalid email or password", 401)

    user_id = str(user_doc["id"])
    now = datetime.now(UTC)
    refresh_id = str(uuid4())
    refresh = create_refresh_token(user_id, refresh_id)
    await db.refresh_tokens.insert_one(
        {
            "id": refresh_id,
            "user_id": user_id,
            "token_hash": hash_password(refresh),
            "expires_at": now + timedelta(days=settings.jwt_refresh_token_expire_days),
            "revoked_at": None,
            "created_at": now,
        }
    )
    return TokenResponse(
        access_token=create_access_token(user_id, str(user_doc.get("role", "responder"))),
        refresh_token=refresh,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshRequest, db: AsyncIOMotorDatabase = Depends(get_db)
) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except ValueError as exc:
        raise AppError("INVALID_REFRESH_TOKEN", "Invalid refresh token", 401) from exc

    token_id = str(claims["jti"])
    token_doc = await db.refresh_tokens.find_one({"id": token_id})
    if token_doc is None or token_doc.get("revoked_at") is not None:
        raise AppError("INVALID_REFRESH_TOKEN", "Invalid refresh token", 401)

    expires_at = token_doc.get("expires_at")
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at and expires_at <= datetime.now(UTC):
        raise AppError("REFRESH_TOKEN_EXPIRED", "Refresh token expired", 401)
    if not verify_password(payload.refresh_token, token_doc.get("token_hash", "")):
        raise AppError("INVALID_REFRESH_TOKEN", "Invalid refresh token", 401)

    user_id = str(token_doc["user_id"])
    user_doc = await db.users.find_one({"id": user_id})
    if user_doc is None or not user_doc.get("is_active", True):
        raise AppError("INVALID_REFRESH_TOKEN", "Invalid refresh token", 401)

    now = datetime.now(UTC)
    await db.refresh_tokens.update_one({"id": token_id}, {"$set": {"revoked_at": now}})

    next_refresh_id = str(uuid4())
    next_refresh = create_refresh_token(user_id, next_refresh_id)
    await db.refresh_tokens.insert_one(
        {
            "id": next_refresh_id,
            "user_id": user_id,
            "token_hash": hash_password(next_refresh),
            "expires_at": now + timedelta(days=settings.jwt_refresh_token_expire_days),
            "revoked_at": None,
            "created_at": now,
        }
    )
    return TokenResponse(
        access_token=create_access_token(user_id, str(user_doc.get("role", "responder"))),
        refresh_token=next_refresh,
    )


@router.post("/logout", status_code=204)
async def logout(payload: RefreshRequest, db: AsyncIOMotorDatabase = Depends(get_db)) -> None:
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except ValueError:
        return None
    token_id = str(claims["jti"])
    await db.refresh_tokens.update_one(
        {"id": token_id, "revoked_at": None}, {"$set": {"revoked_at": datetime.now(UTC)}}
    )
    return None
