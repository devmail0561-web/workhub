"""Dépôts SQLAlchemy pour les utilisateurs et les sessions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, LargeBinary, Text, Uuid, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from workhub.iam.domain.session import Session
from workhub.iam.domain.user import User
from workhub.iam.infrastructure.database import Base
from workhub.shared.api import ConflictError


class AppUserRow(Base):
    """Ligne de la table `app_user`."""

    __tablename__ = "app_user"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False)
    is_admin: Mapped[bool] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionRow(Base):
    """Ligne de la table `session`."""

    __tablename__ = "session"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    refresh_token_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def _to_user(row: AppUserRow) -> User:
    return User(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        display_name=row.display_name,
        is_active=row.is_active,
        is_admin=row.is_admin,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_login_at=row.last_login_at,
    )


class SqlAlchemyUserRepository:
    """Implémentation PostgreSQL du port utilisateur."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_email(self, email: str) -> User | None:
        row = (
            await self._session.execute(
                select(AppUserRow).where(func.lower(AppUserRow.email) == email.lower())
            )
        ).scalar_one_or_none()
        return None if row is None else _to_user(row)

    async def find_by_id(self, user_id: UUID) -> User | None:
        row = await self._session.get(AppUserRow, user_id)
        return None if row is None else _to_user(row)

    async def add(self, user: User) -> None:
        self._session.add(
            AppUserRow(
                id=user.id,
                email=user.email,
                password_hash=user.password_hash,
                display_name=user.display_name,
                is_active=user.is_active,
                is_admin=user.is_admin,
                created_at=user.created_at,
                updated_at=user.updated_at,
                last_login_at=user.last_login_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("Un compte utilise déjà cette adresse e-mail") from exc

    async def record_login(self, user_id: UUID, at: datetime) -> None:
        await self._session.execute(
            update(AppUserRow)
            .where(AppUserRow.id == user_id)
            .values(last_login_at=at, updated_at=at)
        )


class SqlAlchemySessionRepository:
    """Implémentation PostgreSQL du port session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, session: Session) -> None:
        self._session.add(
            SessionRow(
                id=session.id,
                user_id=session.user_id,
                refresh_token_sha256=session.refresh_token_sha256,
                created_at=session.created_at,
                expires_at=session.expires_at,
                last_used_at=session.last_used_at,
                revoked_at=session.revoked_at,
            )
        )
        await self._session.flush()

    async def rotate(
        self,
        token_sha256: bytes,
        new_token_sha256: bytes,
        now: datetime,
        expires_at: datetime,
    ) -> UUID | None:
        result = await self._session.execute(
            update(SessionRow)
            .where(
                SessionRow.refresh_token_sha256 == token_sha256,
                SessionRow.revoked_at.is_(None),
                SessionRow.expires_at > now,
            )
            .values(
                refresh_token_sha256=new_token_sha256,
                last_used_at=now,
                expires_at=expires_at,
            )
            .returning(SessionRow.user_id)
        )
        return result.scalar_one_or_none()

    async def revoke_by_hash(self, token_sha256: bytes, now: datetime) -> None:
        await self._session.execute(
            update(SessionRow)
            .where(
                SessionRow.refresh_token_sha256 == token_sha256,
                SessionRow.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
