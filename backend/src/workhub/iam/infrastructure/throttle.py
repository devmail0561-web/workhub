"""Limitation des tentatives de connexion persistée dans PostgreSQL."""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta

from sqlalchemy import DateTime, LargeBinary, case, delete, func, literal, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from workhub.iam.infrastructure.database import Base
from workhub.shared.api import Clock, RateLimitedError


class LoginAttemptRow(Base):
    """Compteur de tentatives pour une clé d'IP ou de compte."""

    __tablename__ = "login_attempt"

    key_hash: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    failure_count: Mapped[int] = mapped_column(nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyLoginAttemptLimiter:
    """Applique un verrou temporaire par IP et par compte.

    Les écritures utilisent leur propre transaction : une tentative échouée doit rester
    comptabilisée même si la transaction métier de la requête est annulée.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Clock,
        *,
        max_attempts: int,
        window_seconds: int,
        lock_seconds: int,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._lock_seconds = lock_seconds

    async def check(self, *, client_ip: str, email: str) -> None:
        now = self._clock.now()
        async with self._session_factory() as session:
            locked_until = (
                await session.execute(
                    select(func.max(LoginAttemptRow.locked_until)).where(
                        LoginAttemptRow.key_hash.in_(self._keys(client_ip, email)),
                        LoginAttemptRow.locked_until > now,
                    )
                )
            ).scalar_one()
        if locked_until is not None:
            retry_after = max(1, math.ceil((locked_until - now).total_seconds()))
            raise RateLimitedError(
                "Trop de tentatives de connexion",
                details={"retry_after_seconds": retry_after},
            )

    async def record_failure(self, *, client_ip: str, email: str) -> None:
        now = self._clock.now()
        window_start = now - timedelta(seconds=self._window_seconds)
        lock_until = now + timedelta(seconds=self._lock_seconds)
        values = [
            {
                "key_hash": key,
                "failure_count": 1,
                "window_started_at": now,
                "locked_until": None,
                "updated_at": now,
            }
            for key in self._keys(client_ip, email)
        ]
        statement = pg_insert(LoginAttemptRow).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[LoginAttemptRow.key_hash],
            set_={
                "failure_count": case(
                    (LoginAttemptRow.window_started_at < window_start, 1),
                    else_=LoginAttemptRow.failure_count + 1,
                ),
                "window_started_at": case(
                    (LoginAttemptRow.window_started_at < window_start, now),
                    else_=LoginAttemptRow.window_started_at,
                ),
                "locked_until": case(
                    (
                        LoginAttemptRow.window_started_at < window_start,
                        literal(None, type_=DateTime(timezone=True)),
                    ),
                    (LoginAttemptRow.failure_count + 1 >= self._max_attempts, lock_until),
                    else_=LoginAttemptRow.locked_until,
                ),
                "updated_at": now,
            },
        )
        async with self._session_factory() as session:
            await session.execute(statement)
            await session.commit()

    async def reset(self, *, client_ip: str, email: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                delete(LoginAttemptRow).where(
                    LoginAttemptRow.key_hash.in_(self._keys(client_ip, email))
                )
            )
            await session.commit()

    @staticmethod
    def _keys(client_ip: str, email: str) -> tuple[bytes, bytes]:
        ip_key = hashlib.sha256(b"ip\0" + client_ip.encode("utf-8")).digest()
        account_key = hashlib.sha256(b"account\0" + email.encode("utf-8")).digest()
        return ip_key, account_key
