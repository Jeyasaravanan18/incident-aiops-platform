"""User and Authentication Repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Role
from app.models.user import RefreshToken, User


class UserRepository:
    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: UUID) -> User | None:
        return await session.get(User, user_id)

    @staticmethod
    async def get_by_email(session: AsyncSession, email: str) -> User | None:
        stmt = select(User).where(User.email == email.strip().lower())
        return await session.scalar(stmt)

    @staticmethod
    async def list_active(session: AsyncSession) -> list[User]:
        stmt = select(User).where(User.is_active.is_(True)).order_by(User.full_name.asc())
        result = await session.scalars(stmt)
        return list(result.all())

    @staticmethod
    async def create_user(
        session: AsyncSession,
        email: str,
        full_name: str,
        password_hash: str,
        role: Role = Role.VIEWER,
    ) -> User:
        user = User(
            email=email.strip().lower(),
            full_name=full_name.strip(),
            password_hash=password_hash,
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        return user

    @staticmethod
    async def create_refresh_token(
        session: AsyncSession,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        session.add(token)
        await session.flush()
        return token

    @staticmethod
    async def get_refresh_token(session: AsyncSession, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return await session.scalar(stmt)

    @staticmethod
    async def revoke_refresh_token(session: AsyncSession, token: RefreshToken) -> None:
        from datetime import UTC

        token.revoked_at = datetime.now(UTC)
        await session.flush()
