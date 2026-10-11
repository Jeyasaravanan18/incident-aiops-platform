from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

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
from app.models.enums import Role
from app.models.user import RefreshToken
from app.repositories.user_repo import UserRepository
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    payload: RegisterRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    email_str = str(payload.email).strip().lower()
    existing = await UserRepository.get_by_email(session, email_str)
    if existing:
        raise AppError("EMAIL_ALREADY_REGISTERED", "Email already registered", 409)

    user = await UserRepository.create_user(
        session=session,
        email=email_str,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=Role(payload.role) if isinstance(payload.role, str) else payload.role,
    )

    refresh_id = uuid4()
    refresh = create_refresh_token(user.id, refresh_id)
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=settings.jwt_refresh_token_expire_days)

    await UserRepository.create_refresh_token(
        session=session,
        user_id=user.id,
        token_hash=hash_password(refresh),
        expires_at=expires_at,
    )

    return TokenResponse(
        access_token=create_access_token(user.id, str(user.role.value)),
        refresh_token=refresh,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    email_str = str(payload.email).strip().lower()
    user = await UserRepository.get_by_email(session, email_str)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Invalid email or password", 401)

    if not user.is_active:
        raise AppError("USER_INACTIVE", "Account is deactivated", 401)

    refresh_id = uuid4()
    refresh = create_refresh_token(user.id, refresh_id)
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=settings.jwt_refresh_token_expire_days)

    await UserRepository.create_refresh_token(
        session=session,
        user_id=user.id,
        token_hash=hash_password(refresh),
        expires_at=expires_at,
    )

    return TokenResponse(
        access_token=create_access_token(user.id, str(user.role.value)),
        refresh_token=refresh,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except ValueError as exc:
        raise AppError("INVALID_REFRESH_TOKEN", "Invalid refresh token", 401) from exc

    user_id = UUID(str(claims["sub"]))
    user = await UserRepository.get_by_id(session, user_id)
    if user is None or not user.is_active:
        raise AppError("INVALID_REFRESH_TOKEN", "Invalid refresh token", 401)

    # Validate active refresh token from DB
    stmt = (
        select(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .where(RefreshToken.revoked_at.is_(None))
    )
    tokens = list((await session.scalars(stmt)).all())

    matching_token: RefreshToken | None = None
    for t in tokens:
        if verify_password(payload.refresh_token, t.token_hash):
            matching_token = t
            break

    if matching_token is None:
        raise AppError("INVALID_REFRESH_TOKEN", "Invalid refresh token", 401)

    now = datetime.now(UTC)
    expires_at = matching_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at <= now:
        raise AppError("REFRESH_TOKEN_EXPIRED", "Refresh token expired", 401)

    # Revoke current token (rotation)
    matching_token.revoked_at = now

    # Issue new token pair
    next_refresh_id = uuid4()
    next_refresh = create_refresh_token(user.id, next_refresh_id)
    next_expires = now + timedelta(days=settings.jwt_refresh_token_expire_days)

    await UserRepository.create_refresh_token(
        session=session,
        user_id=user.id,
        token_hash=hash_password(next_refresh),
        expires_at=next_expires,
    )

    return TokenResponse(
        access_token=create_access_token(user.id, str(user.role.value)),
        refresh_token=next_refresh,
    )


@router.post("/logout", status_code=204)
async def logout(payload: RefreshRequest, session: AsyncSession = Depends(get_session)) -> None:
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
        user_id = UUID(str(claims["sub"]))
        stmt = (
            select(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .where(RefreshToken.revoked_at.is_(None))
        )
        tokens = list((await session.scalars(stmt)).all())
        now = datetime.now(UTC)
        for t in tokens:
            if verify_password(payload.refresh_token, t.token_hash):
                t.revoked_at = now
                break
    except Exception:
        pass
