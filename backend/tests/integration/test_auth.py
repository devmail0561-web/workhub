from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from workhub.iam.application.auth import AuthService
from workhub.iam.application.bootstrap import bootstrap_admin
from workhub.iam.bootstrap import main
from workhub.iam.infrastructure.repositories import (
    SessionRow,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
)
from workhub.iam.infrastructure.security import (
    Argon2PasswordHasher,
    JwtTokenIssuer,
    OpaqueRefreshTokenFactory,
)
from workhub.shared.api import AuthenticationError, SystemClock

pytestmark = pytest.mark.integration

SECRET = "test-secret-key-0123456789abcdef"


def _service(session: AsyncSession) -> AuthService:
    return AuthService(
        users=SqlAlchemyUserRepository(session),
        sessions=SqlAlchemySessionRepository(session),
        password_hasher=Argon2PasswordHasher(),
        token_issuer=JwtTokenIssuer(SECRET),
        refresh_tokens=OpaqueRefreshTokenFactory(),
        clock=SystemClock(),
        access_token_ttl_seconds=900,
        refresh_token_ttl_seconds=3600,
    )


async def test_admin_login_refresh_rotation_and_logout(session: AsyncSession) -> None:
    email = f"admin-{uuid4()}@example.test"
    admin = await bootstrap_admin(
        users=SqlAlchemyUserRepository(session),
        password_hasher=Argon2PasswordHasher(),
        clock=SystemClock(),
        email=email,
        display_name="Ada",
        password="correct-horse-battery",
    )
    await session.commit()
    assert admin.is_admin is True

    service = _service(session)
    login = await service.login(email, "correct-horse-battery")
    await session.commit()
    assert login.refresh_token

    count = (await session.execute(select(func.count()).select_from(SessionRow))).scalar_one()
    assert count == 1

    rotated = await service.refresh(login.refresh_token)
    await session.commit()
    assert rotated.refresh_token != login.refresh_token
    with pytest.raises(AuthenticationError):
        await service.refresh(login.refresh_token)

    await service.logout(rotated.refresh_token)
    await session.commit()
    with pytest.raises(AuthenticationError):
        await service.refresh(rotated.refresh_token)


def test_bootstrap_cli_creates_an_admin(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_database)
    monkeypatch.setenv("WORKHUB_BOOTSTRAP_PASSWORD", "correct-horse-battery")
    email = f"cli-{uuid4()}@example.test"

    assert main(["--email", email, "--display-name", "CLI"]) == 0
    assert main(["--email", email, "--display-name", "CLI"]) == 1
