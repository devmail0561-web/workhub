from __future__ import annotations

import pytest
from tests.unit.iam.fakes import (
    FakeClock,
    FakePasswordHasher,
    FakeRefreshTokenFactory,
    FakeSessionRepository,
    FakeTokenIssuer,
    FakeUserRepository,
    make_user,
)

from workhub.iam.application.auth import AuthService
from workhub.iam.application.bootstrap import bootstrap_admin
from workhub.shared.api import AuthenticationError, ConflictError, ValidationError


def build_service(
    *,
    users: FakeUserRepository | None = None,
    sessions: FakeSessionRepository | None = None,
    clock: FakeClock | None = None,
    hasher: FakePasswordHasher | None = None,
) -> AuthService:
    return AuthService(
        users=users or FakeUserRepository(),
        sessions=sessions or FakeSessionRepository(),
        password_hasher=hasher or FakePasswordHasher(),
        token_issuer=FakeTokenIssuer(),
        refresh_tokens=FakeRefreshTokenFactory(),
        clock=clock or FakeClock(),
        access_token_ttl_seconds=900,
        refresh_token_ttl_seconds=3600,
    )


async def test_bootstrap_creates_an_admin_with_hashed_password() -> None:
    users = FakeUserRepository()
    hasher = FakePasswordHasher()
    view = await bootstrap_admin(
        users=users,
        password_hasher=hasher,
        clock=FakeClock(),
        email="  Admin@Example.Test ",
        display_name="  Ada  ",
        password="correct-horse-battery",
    )

    assert view.email == "admin@example.test"
    assert view.display_name == "Ada"
    assert view.is_admin is True
    stored = users.users[view.id]
    assert stored.password_hash == "hash:correct-horse-battery"


async def test_bootstrap_refuses_duplicate_email_and_weak_password() -> None:
    users = FakeUserRepository()
    await bootstrap_admin(
        users=users,
        password_hasher=FakePasswordHasher(),
        clock=FakeClock(),
        email="admin@example.test",
        display_name="Ada",
        password="correct-horse-battery",
    )

    with pytest.raises(ConflictError):
        await bootstrap_admin(
            users=users,
            password_hasher=FakePasswordHasher(),
            clock=FakeClock(),
            email="ADMIN@example.test",
            display_name="Ada",
            password="correct-horse-battery",
        )

    with pytest.raises(ValidationError):
        await bootstrap_admin(
            users=FakeUserRepository(),
            password_hasher=FakePasswordHasher(),
            clock=FakeClock(),
            email="other@example.test",
            display_name="Ada",
            password="court",
        )


async def test_login_opens_a_session_and_updates_last_login() -> None:
    users = FakeUserRepository()
    sessions = FakeSessionRepository()
    clock = FakeClock()
    user = make_user()
    users.users[user.id] = user
    service = build_service(users=users, sessions=sessions, clock=clock)

    result = await service.login("ADMIN@example.test", "correct-horse-battery")

    assert result.user.id == user.id
    assert result.access_token.startswith("access:")
    assert result.refresh_token == "refresh-1"
    assert users.users[user.id].last_login_at == clock.now()
    assert b"refresh-1" in sessions.sessions


async def test_login_rejects_unknown_inactive_and_wrong_password() -> None:
    hasher = FakePasswordHasher()
    service = build_service(hasher=hasher)
    with pytest.raises(AuthenticationError):
        await service.login("unknown@example.test", "whatever")
    assert hasher.dummy_checks == 1

    users = FakeUserRepository()
    inactive = make_user(email="inactive@example.test", is_active=False)
    users.users[inactive.id] = inactive
    service = build_service(users=users, hasher=hasher)
    with pytest.raises(AuthenticationError):
        await service.login(inactive.email, "correct-horse-battery")

    users = FakeUserRepository()
    user = make_user()
    users.users[user.id] = user
    service = build_service(users=users, hasher=hasher)
    with pytest.raises(AuthenticationError):
        await service.login(user.email, "wrong-password")


async def test_refresh_rotates_the_token_and_rejects_the_old_one() -> None:
    users = FakeUserRepository()
    user = make_user()
    users.users[user.id] = user
    service = build_service(users=users)
    login = await service.login(user.email, "correct-horse-battery")

    refreshed = await service.refresh(login.refresh_token)

    assert refreshed.refresh_token != login.refresh_token
    assert refreshed.user.id == user.id
    with pytest.raises(AuthenticationError):
        await service.refresh(login.refresh_token)
    with pytest.raises(AuthenticationError):
        await service.refresh("inconnu")


async def test_refresh_rejects_an_expired_session() -> None:
    users = FakeUserRepository()
    user = make_user()
    users.users[user.id] = user
    clock = FakeClock()
    service = build_service(users=users, clock=clock)
    login = await service.login(user.email, "correct-horse-battery")
    clock.advance(3600)

    with pytest.raises(AuthenticationError):
        await service.refresh(login.refresh_token)


async def test_logout_revokes_the_session_idempotently() -> None:
    users = FakeUserRepository()
    user = make_user()
    users.users[user.id] = user
    service = build_service(users=users)
    login = await service.login(user.email, "correct-horse-battery")

    await service.logout(login.refresh_token)
    await service.logout(login.refresh_token)

    with pytest.raises(AuthenticationError):
        await service.refresh(login.refresh_token)


async def test_authenticate_rejects_inactive_users() -> None:
    users = FakeUserRepository()
    user = make_user()
    users.users[user.id] = user
    service = build_service(users=users)
    login = await service.login(user.email, "correct-horse-battery")

    view = await service.authenticate(login.access_token)
    assert view.id == user.id

    users.users[user.id] = make_user(email=user.email, is_active=False)
    with pytest.raises(AuthenticationError):
        await service.authenticate(login.access_token)
