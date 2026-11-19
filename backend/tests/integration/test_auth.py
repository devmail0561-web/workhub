from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from tests.unit.iam.fakes import FakeClock, FakeLoginAttemptLimiter

from workhub.iam.application.auth import AuthService
from workhub.iam.application.bootstrap import bootstrap_admin
from workhub.iam.application.ports import LoginAttemptLimiter
from workhub.iam.bootstrap import main
from workhub.iam.infrastructure.database import create_session_factory
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
from workhub.iam.infrastructure.throttle import SqlAlchemyLoginAttemptLimiter
from workhub.shared.api import (
    AuthenticationError,
    Clock,
    RateLimitedError,
    SystemClock,
)

pytestmark = pytest.mark.integration

SECRET = "test-secret-key-0123456789abcdef"


def _service(
    session: AsyncSession,
    *,
    limiter: LoginAttemptLimiter | None = None,
    clock: Clock | None = None,
) -> AuthService:
    return AuthService(
        users=SqlAlchemyUserRepository(session),
        sessions=SqlAlchemySessionRepository(session),
        login_attempts=limiter or FakeLoginAttemptLimiter(FakeClock()),
        password_hasher=Argon2PasswordHasher(),
        token_issuer=JwtTokenIssuer(SECRET),
        refresh_tokens=OpaqueRefreshTokenFactory(),
        clock=clock or SystemClock(),
        access_token_ttl_seconds=900,
        refresh_token_ttl_seconds=3600,
        commit=session.commit,
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
    login = await service.login(email, "correct-horse-battery", "203.0.113.1")
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


async def test_login_locks_temporarily_by_account_and_ip(
    session: AsyncSession,
    engine: AsyncEngine,
) -> None:
    email = f"lock-{uuid4()}@example.test"
    password = "correct-horse-battery"
    await bootstrap_admin(
        users=SqlAlchemyUserRepository(session),
        password_hasher=Argon2PasswordHasher(),
        clock=SystemClock(),
        email=email,
        display_name="Ada",
        password=password,
    )
    other = await bootstrap_admin(
        users=SqlAlchemyUserRepository(session),
        password_hasher=Argon2PasswordHasher(),
        clock=SystemClock(),
        email=f"other-{uuid4()}@example.test",
        display_name="Grace",
        password=password,
    )
    await session.commit()

    clock = FakeClock()
    limiter = SqlAlchemyLoginAttemptLimiter(
        create_session_factory(engine),
        clock,
        max_attempts=3,
        window_seconds=60,
        lock_seconds=60,
    )
    service = _service(session, limiter=limiter, clock=clock)
    client_ip = "203.0.113.10"

    for _ in range(3):
        with pytest.raises(AuthenticationError):
            await service.login(email, "faux", client_ip)

    with pytest.raises(RateLimitedError) as blocked:
        await service.login(email, password, client_ip)
    assert blocked.value.details["retry_after_seconds"] == 60

    with pytest.raises(RateLimitedError):
        await service.login(email, password, "203.0.113.11")

    with pytest.raises(RateLimitedError):
        await service.login(other.email, password, client_ip)

    clock.advance(60)
    login = await service.login(email, password, client_ip)
    await session.commit()
    assert login.user.email == email


def test_bootstrap_cli_creates_an_admin(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_database)
    monkeypatch.setenv("WORKHUB_BOOTSTRAP_PASSWORD", "correct-horse-battery")
    email = f"cli-{uuid4()}@example.test"

    assert main(["--email", email, "--display-name", "CLI"]) == 0
    assert main(["--email", email, "--display-name", "CLI"]) == 1
