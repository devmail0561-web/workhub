from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from workhub.iam.infrastructure.security import (
    Argon2PasswordHasher,
    JwtTokenIssuer,
    OpaqueRefreshTokenFactory,
)
from workhub.shared.api import AuthenticationError

SECRET = "test-secret-key-0123456789abcdef"


def test_argon2id_hash_and_verify() -> None:
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash("correct-horse-battery")

    assert hashed.startswith("$argon2id$")
    assert hasher.verify(hashed, "correct-horse-battery") is True
    assert hasher.verify(hashed, "mauvais") is False
    assert hasher.verify("pas-un-hash", "correct-horse-battery") is False
    hasher.verify_dummy("n-importe-quoi")


def test_jwt_access_token_roundtrip_and_expiration() -> None:
    issuer = JwtTokenIssuer(SECRET)
    user_id = uuid4()
    now = datetime.now(UTC)

    token = issuer.issue_access_token(user_id, now, 900)
    assert issuer.decode_access_token(token.value) == user_id

    expired = issuer.issue_access_token(
        user_id,
        datetime.now(UTC) - timedelta(seconds=10),
        1,
    )
    with pytest.raises(AuthenticationError):
        issuer.decode_access_token(expired.value)


def test_jwt_rejects_tampering_and_wrong_token_type() -> None:
    issuer = JwtTokenIssuer(SECRET)
    user_id = uuid4()
    now = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    token = issuer.issue_access_token(user_id, now, 900)

    with pytest.raises(AuthenticationError):
        issuer.decode_access_token(f"{token.value}x")
    with pytest.raises(AuthenticationError):
        issuer.decode_access_token(
            jwt.encode(  # pyright: ignore[reportUnknownMemberType]
                {"sub": str(user_id)}, SECRET, algorithm="HS256"
            )
        )


def test_refresh_tokens_are_opaque_and_hashed() -> None:
    factory = OpaqueRefreshTokenFactory()
    first, first_hash = factory.new_token()
    second, second_hash = factory.new_token()

    assert first != second
    assert len(first_hash) == 32
    assert first_hash == factory.hash_token(first)
    assert second_hash == factory.hash_token(second)
