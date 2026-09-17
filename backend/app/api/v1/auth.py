from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import RefreshToken, User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    payload: RegisterRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    existing = await session.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise AppError("EMAIL_ALREADY_REGISTERED", "Email already registered", 409)
    user = User(
        email=str(payload.email),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    await session.flush()
    refresh_id = uuid4()
    refresh = create_refresh_token(user.id, refresh_id)
    session.add(
        RefreshToken(
            id=refresh_id,
            user_id=user.id,
            token_hash=hash_password(refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days),
        )
    )
    await session.commit()
    return TokenResponse(
        access_token=create_access_token(user.id, str(user.role)), refresh_token=refresh
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    user = await session.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Invalid email or password", 401)
    refresh_id = uuid4()
    refresh = create_refresh_token(user.id, refresh_id)
    session.add(
        RefreshToken(
            id=refresh_id,
            user_id=user.id,
            token_hash=hash_password(refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days),
        )
    )
    await session.commit()
    return TokenResponse(
        access_token=create_access_token(user.id, str(user.role)), refresh_token=refresh
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except ValueError as exc:
        raise AppError("INVALID_REFRESH_TOKEN", "Invalid refresh token", 401) from exc

    token = await session.get(RefreshToken, claims["jti"])
    if token is None or token.revoked_at is not None:
        raise AppError("INVALID_REFRESH_TOKEN", "Invalid refresh token", 401)
    if token.expires_at <= datetime.now(UTC):
        raise AppError("REFRESH_TOKEN_EXPIRED", "Refresh token expired", 401)
    if not verify_password(payload.refresh_token, token.token_hash):
        raise AppError("INVALID_REFRESH_TOKEN", "Invalid refresh token", 401)

    user = await session.get(User, token.user_id)
    if user is None or not user.is_active:
        raise AppError("INVALID_REFRESH_TOKEN", "Invalid refresh token", 401)

    token.revoked_at = datetime.now(UTC)
    next_refresh_id = uuid4()
    next_refresh = create_refresh_token(user.id, next_refresh_id)
    session.add(
        RefreshToken(
            id=next_refresh_id,
            user_id=user.id,
            token_hash=hash_password(next_refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days),
        )
    )
    await session.commit()
    return TokenResponse(
        access_token=create_access_token(user.id, str(user.role)),
        refresh_token=next_refresh,
    )


@router.post("/logout", status_code=204)
async def logout(payload: RefreshRequest, session: AsyncSession = Depends(get_session)) -> None:
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except ValueError:
        return None
    token = await session.get(RefreshToken, claims["jti"])
    if token is not None and token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        await session.commit()
    return None
