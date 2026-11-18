"""Doubles en mémoire pour tester l'authentification sans base ni HTTP."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from workhub.iam.application.ports import AccessToken
from workhub.iam.domain.session import Session
from workhub.iam.domain.user import User
from workhub.shared.api import AuthenticationError, RateLimitedError


class FakeClock:
    def __init__(self, now: datetime | None = None) -> None:
        self.current = now or datetime(2026, 11, 17, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


class FakeLoginAttemptLimiter:
    def __init__(
        self,
        clock: FakeClock,
        *,
        max_attempts: int = 5,
        lock_seconds: int = 60,
    ) -> None:
        self.clock = clock
        self.max_attempts = max_attempts
        self.lock_seconds = lock_seconds
        self.failures: dict[tuple[str, str], int] = {}
        self.locks: dict[tuple[str, str], datetime] = {}

    @staticmethod
    def _keys(client_ip: str, email: str) -> tuple[tuple[str, str], ...]:
        return (("ip", client_ip), ("account", email.lower()))

    async def check(self, *, client_ip: str, email: str) -> None:
        now = self.clock.now()
        for key in self._keys(client_ip, email):
            locked_until = self.locks.get(key)
            if locked_until is not None and locked_until > now:
                retry_after = max(1, math.ceil((locked_until - now).total_seconds()))
                raise RateLimitedError(
                    "Trop de tentatives de connexion",
                    details={"retry_after_seconds": retry_after},
                )

    async def record_failure(self, *, client_ip: str, email: str) -> None:
        now = self.clock.now()
        for key in self._keys(client_ip, email):
            failures = self.failures.get(key, 0) + 1
            self.failures[key] = failures
            if failures >= self.max_attempts:
                self.locks[key] = now + timedelta(seconds=self.lock_seconds)

    async def reset(self, *, client_ip: str, email: str) -> None:
        for key in self._keys(client_ip, email):
            self.failures.pop(key, None)
            self.locks.pop(key, None)


class FakePasswordHasher:
    def __init__(self) -> None:
        self.dummy_checks = 0

    def hash(self, password: str) -> str:
        return f"hash:{password}"

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == self.hash(password)

    def verify_dummy(self, password: str) -> None:
        self.dummy_checks += 1


class FakeTokenIssuer:
    def issue_access_token(
        self,
        user_id: UUID,
        now: datetime,
        ttl_seconds: int,
    ) -> AccessToken:
        expires_at = now + timedelta(seconds=ttl_seconds)
        return AccessToken(
            value=f"access:{user_id}:{int(expires_at.timestamp())}",
            expires_at=expires_at,
        )

    def decode_access_token(self, token: str) -> UUID:
        parts = token.split(":")
        if len(parts) != 3 or parts[0] != "access":
            raise AuthenticationError("Jeton invalide ou expiré")
        return UUID(parts[1])


class FakeRefreshTokenFactory:
    def __init__(self) -> None:
        self.counter = 0

    def new_token(self) -> tuple[str, bytes]:
        self.counter += 1
        token = f"refresh-{self.counter}"
        return token, self.hash_token(token)

    def hash_token(self, token: str) -> bytes:
        return token.encode("utf-8")


class FakeUserRepository:
    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}

    async def find_by_email(self, email: str) -> User | None:
        return next(
            (user for user in self.users.values() if user.email == email.lower()),
            None,
        )

    async def find_by_id(self, user_id: UUID) -> User | None:
        return self.users.get(user_id)

    async def add(self, user: User) -> None:
        self.users[user.id] = user

    async def record_login(self, user_id: UUID, at: datetime) -> None:
        self.users[user_id] = self.users[user_id].record_login(at)


class FakeSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[bytes, Session] = {}

    async def create(self, session: Session) -> None:
        self.sessions[session.refresh_token_sha256] = session

    async def rotate(
        self,
        token_sha256: bytes,
        new_token_sha256: bytes,
        now: datetime,
        expires_at: datetime,
    ) -> UUID | None:
        session = self.sessions.get(token_sha256)
        if session is None or session.revoked_at is not None or session.expires_at <= now:
            return None
        del self.sessions[token_sha256]
        self.sessions[new_token_sha256] = Session(
            id=session.id,
            user_id=session.user_id,
            refresh_token_sha256=new_token_sha256,
            created_at=session.created_at,
            expires_at=expires_at,
            last_used_at=now,
        )
        return session.user_id

    async def revoke_by_hash(self, token_sha256: bytes, now: datetime) -> None:
        session = self.sessions.get(token_sha256)
        if session is None or session.revoked_at is not None:
            return
        self.sessions[token_sha256] = Session(
            id=session.id,
            user_id=session.user_id,
            refresh_token_sha256=session.refresh_token_sha256,
            created_at=session.created_at,
            expires_at=session.expires_at,
            last_used_at=session.last_used_at,
            revoked_at=now,
        )


def make_user(
    *,
    email: str = "admin@example.test",
    password: str = "correct-horse-battery",
    is_active: bool = True,
    is_admin: bool = True,
) -> User:
    now = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)
    return User(
        id=uuid4(),
        email=email,
        password_hash=f"hash:{password}",
        display_name="Admin",
        is_active=is_active,
        is_admin=is_admin,
        created_at=now,
        updated_at=now,
    )
