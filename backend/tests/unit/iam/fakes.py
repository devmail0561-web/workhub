"""Doubles en mémoire pour tester l'authentification sans base ni HTTP."""

from __future__ import annotations

import hashlib
import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from workhub.iam.application.integration_ports import TokenIdentity
from workhub.iam.application.ports import AccessToken
from workhub.iam.domain.api_token import ApiToken
from workhub.iam.domain.integration import Integration, IntegrationKind
from workhub.iam.domain.session import Session
from workhub.iam.domain.user import User
from workhub.shared.api import (
    AuthenticationError,
    Principal,
    PrincipalType,
    RateLimitedError,
)


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


class FakeApiTokenFactory:
    def __init__(self) -> None:
        self.counter = 0

    def new_token(self) -> tuple[str, bytes]:
        self.counter += 1
        token = f"whub_token-{self.counter}"
        return token, self.hash_token(token)

    def hash_token(self, token: str) -> bytes:
        return hashlib.sha256(token.encode("utf-8")).digest()

    def is_api_token(self, token: str) -> bool:
        return token.startswith("whub_")


class FakeIntegrationRepository:
    def __init__(self) -> None:
        self.integrations: dict[UUID, Integration] = {}

    async def add(self, integration: Integration) -> None:
        self.integrations[integration.id] = integration

    async def find_by_id(self, integration_id: UUID) -> Integration | None:
        return self.integrations.get(integration_id)

    async def list_for_owner(self, owner_id: UUID) -> list[Integration]:
        return sorted(
            (item for item in self.integrations.values() if item.owner_id == owner_id),
            key=lambda item: item.created_at,
            reverse=True,
        )

    async def revoke(self, integration_id: UUID, at: datetime) -> None:
        integration = self.integrations.get(integration_id)
        if integration is not None:
            self.integrations[integration_id] = integration.revoke(at)


class FakeApiTokenRepository:
    def __init__(self, integrations: FakeIntegrationRepository | None = None) -> None:
        self.tokens: dict[UUID, ApiToken] = {}
        self.integrations = integrations or FakeIntegrationRepository()

    async def add(self, token: ApiToken) -> None:
        self.tokens[token.id] = token

    async def find_by_id(self, token_id: UUID) -> ApiToken | None:
        return self.tokens.get(token_id)

    async def find_active_by_hash(
        self,
        token_sha256: bytes,
        now: datetime,
    ) -> TokenIdentity | None:
        for token in self.tokens.values():
            integration = self.integrations.integrations.get(token.integration_id)
            if (
                token.token_sha256 == token_sha256
                and token.is_active(now)
                and integration is not None
                and integration.is_active
            ):
                return TokenIdentity(token=token, integration=integration)
        return None

    async def revoke(self, token_id: UUID, at: datetime) -> None:
        token = self.tokens.get(token_id)
        if token is not None:
            self.tokens[token_id] = token.revoke(at)

    async def revoke_for_integration(self, integration_id: UUID, at: datetime) -> None:
        for token_id, token in list(self.tokens.items()):
            if token.integration_id == integration_id:
                self.tokens[token_id] = token.revoke(at)

    async def touch_last_used(self, token_id: UUID, at: datetime) -> None:
        token = self.tokens.get(token_id)
        if token is not None:
            self.tokens[token_id] = replace(token, last_used_at=at)


def make_integration(
    *,
    owner_id: UUID,
    name: str = "OpenCode",
    clock: FakeClock | None = None,
) -> Integration:
    now = (clock or FakeClock()).now()
    return Integration(
        id=uuid4(),
        name=name,
        kind=IntegrationKind.OPENCODE,
        owner_id=owner_id,
        created_at=now,
    )


def make_principal(
    *,
    is_admin: bool = True,
    scopes: frozenset[str] | None = None,
    display_name: str = "Admin",
) -> Principal:
    if scopes is None:
        scopes = frozenset({"*"}) if is_admin else frozenset()
    return Principal(
        id=uuid4(),
        type=PrincipalType.USER,
        display_name=display_name,
        scopes=scopes,
    )


class FakePrincipalResolver:
    def __init__(self, principal: Principal, *, token: str = "access") -> None:
        self.principal = principal
        self.token = token

    async def resolve(self, credential: str) -> Principal:
        if credential != self.token:
            raise AuthenticationError("Jeton invalide ou expiré")
        return self.principal
