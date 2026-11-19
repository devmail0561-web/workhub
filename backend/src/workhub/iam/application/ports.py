"""Ports de l'authentification, indépendants de PostgreSQL et de HTTP."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from workhub.iam.domain.session import Session
from workhub.iam.domain.user import User

type Commit = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class AccessToken:
    """JWT d'accès signé et sa date d'expiration."""

    value: str
    expires_at: datetime


class UserRepository(Protocol):
    """Accès aux comptes humains."""

    async def find_by_email(self, email: str) -> User | None: ...

    async def find_by_id(self, user_id: UUID) -> User | None: ...

    async def add(self, user: User) -> None: ...

    async def record_login(self, user_id: UUID, at: datetime) -> None: ...


class SessionRepository(Protocol):
    """Accès aux sessions de rafraîchissement."""

    async def create(self, session: Session) -> None: ...

    async def rotate(
        self,
        token_sha256: bytes,
        new_token_sha256: bytes,
        now: datetime,
        expires_at: datetime,
    ) -> UUID | None: ...

    async def revoke_by_hash(self, token_sha256: bytes, now: datetime) -> None: ...


class LoginAttemptLimiter(Protocol):
    """Limitation des tentatives de connexion par IP et par compte."""

    async def check(self, *, client_ip: str, email: str) -> None: ...

    async def record_failure(self, *, client_ip: str, email: str) -> None: ...

    async def reset(self, *, client_ip: str, email: str) -> None: ...


class PasswordHasher(Protocol):
    """Hachage et vérification des mots de passe."""

    async def hash(self, password: str) -> str: ...

    async def verify(self, password_hash: str, password: str) -> bool: ...

    async def verify_dummy(self, password: str) -> None: ...


class TokenIssuer(Protocol):
    """Émission et vérification des jetons d'accès."""

    def issue_access_token(
        self,
        user_id: UUID,
        now: datetime,
        ttl_seconds: int,
    ) -> AccessToken: ...

    def decode_access_token(self, token: str) -> UUID: ...


class RefreshTokenFactory(Protocol):
    """Création et hachage des refresh tokens opaques."""

    def new_token(self) -> tuple[str, bytes]: ...

    def hash_token(self, token: str) -> bytes: ...
