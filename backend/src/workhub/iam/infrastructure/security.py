"""Adaptateurs cryptographiques : argon2id, JWT HS256 et refresh tokens opaques."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher as Argon2
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from workhub.iam.application.ports import AccessToken
from workhub.iam.domain.api_token import API_TOKEN_PREFIX
from workhub.shared.api import AuthenticationError

_ACCESS_TOKEN_TYPE = "access"
_DUMMY_PASSWORD = "workhub-dummy-password"


def _argon2() -> Argon2:
    return Argon2(
        time_cost=3,
        memory_cost=65_536,
        parallelism=4,
        hash_len=32,
        salt_len=16,
    )


class Argon2PasswordHasher:
    """Hash argon2id avec les paramètres OWASP recommandés."""

    def __init__(self) -> None:
        self._hasher = _argon2()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False

    def verify_dummy(self, password: str) -> None:
        """Consomme un temps comparable quand l'utilisateur n'existe pas."""
        self.verify(_dummy_hash(), password)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return _argon2().hash(_DUMMY_PASSWORD)


class JwtTokenIssuer:
    """Émet et vérifie des JWT d'accès courts, signés HS256."""

    def __init__(self, secret_key: str) -> None:
        self._secret_key = secret_key

    def issue_access_token(
        self,
        user_id: UUID,
        now: datetime,
        ttl_seconds: int,
    ) -> AccessToken:
        expires_at = now + timedelta(seconds=ttl_seconds)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "typ": _ACCESS_TOKEN_TYPE,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        return AccessToken(
            value=jwt.encode(  # pyright: ignore[reportUnknownMemberType]
                payload,
                self._secret_key,
                algorithm="HS256",
            ),
            expires_at=expires_at,
        )

    def decode_access_token(self, token: str) -> UUID:
        try:
            payload = jwt.decode(  # pyright: ignore[reportUnknownMemberType]
                token,
                self._secret_key,
                algorithms=["HS256"],
                options={"require": ["sub", "typ", "iat", "exp"]},
            )
        except jwt.InvalidTokenError as exc:
            raise AuthenticationError("Jeton invalide ou expiré") from exc

        if payload.get("typ") != _ACCESS_TOKEN_TYPE:
            raise AuthenticationError("Jeton invalide ou expiré")
        subject = payload.get("sub")
        try:
            return UUID(subject) if isinstance(subject, str) else _invalid_subject()
        except ValueError as exc:
            raise AuthenticationError("Jeton invalide ou expiré") from exc


def _invalid_subject() -> UUID:
    raise ValueError("sub absent")


class OpaqueRefreshTokenFactory:
    """Génère un secret opaque et son empreinte SHA-256 pour la base."""

    def new_token(self) -> tuple[str, bytes]:
        token = secrets.token_urlsafe(48)
        return token, self.hash_token(token)

    def hash_token(self, token: str) -> bytes:
        return hashlib.sha256(token.encode("utf-8")).digest()


class OpaqueApiTokenFactory:
    """Génère un jeton d'intégration préfixé et son empreinte SHA-256."""

    def new_token(self) -> tuple[str, bytes]:
        token = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
        return token, self.hash_token(token)

    def hash_token(self, token: str) -> bytes:
        return hashlib.sha256(token.encode("utf-8")).digest()

    def is_api_token(self, token: str) -> bool:
        return token.startswith(API_TOKEN_PREFIX)
