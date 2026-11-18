from __future__ import annotations

from collections.abc import AsyncIterator
from http.cookies import SimpleCookie

import httpx
import pytest
from tests.unit.iam.fakes import (
    FakeClock,
    FakeLoginAttemptLimiter,
    FakePasswordHasher,
    FakeRefreshTokenFactory,
    FakeSessionRepository,
    FakeTokenIssuer,
    FakeUserRepository,
    make_user,
)

from workhub.iam.api import get_auth_service
from workhub.iam.application.auth import AuthService
from workhub.interfaces.rest.app import app

COOKIE_NAME = "workhub_refresh"


@pytest.fixture
def auth_service() -> AuthService:
    users = FakeUserRepository()
    user = make_user()
    users.users[user.id] = user
    clock = FakeClock()
    return AuthService(
        users=users,
        sessions=FakeSessionRepository(),
        login_attempts=FakeLoginAttemptLimiter(clock, max_attempts=3),
        password_hasher=FakePasswordHasher(),
        token_issuer=FakeTokenIssuer(),
        refresh_tokens=FakeRefreshTokenFactory(),
        clock=clock,
        access_token_ttl_seconds=900,
        refresh_token_ttl_seconds=3600,
    )


@pytest.fixture
async def client(auth_service: AuthService) -> AsyncIterator[httpx.AsyncClient]:
    async def override() -> AsyncIterator[AuthService]:
        yield auth_service

    app.dependency_overrides[get_auth_service] = override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def _cookie(response: httpx.Response) -> SimpleCookie:
    cookie: SimpleCookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie


async def test_login_sets_an_http_only_strict_cookie(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.test", "password": "correct-horse-battery"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    assert body["user"]["email"] == "admin@example.test"
    assert "refresh_token" not in body
    cookie = _cookie(response)
    morsel = cookie[COOKIE_NAME]
    assert morsel["httponly"] is True
    assert morsel["samesite"] == "strict"
    assert morsel["path"] == "/api/v1/auth"
    assert morsel["max-age"] == "3600"


async def test_refresh_rotates_and_logout_clears_the_cookie(client: httpx.AsyncClient) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.test", "password": "correct-horse-battery"},
    )
    old_cookie = _cookie(login)[COOKIE_NAME].value

    refreshed = await client.post("/api/v1/auth/refresh")

    assert refreshed.status_code == 200
    new_cookie = _cookie(refreshed)[COOKIE_NAME].value
    assert new_cookie != old_cookie

    logged_out = await client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 204
    assert COOKIE_NAME not in client.cookies

    after_logout = await client.post("/api/v1/auth/refresh")
    assert after_logout.status_code == 401


async def test_login_rejects_bad_credentials_and_missing_refresh(
    client: httpx.AsyncClient,
) -> None:
    bad_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.test", "password": "faux"},
    )
    assert bad_login.status_code == 401
    assert bad_login.json()["error"]["code"] == "authentication_required"

    no_cookie = await client.post("/api/v1/auth/refresh")
    assert no_cookie.status_code == 401


async def test_login_is_rate_limited_with_retry_after(client: httpx.AsyncClient) -> None:
    for _ in range(3):
        failed = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.test", "password": "faux"},
        )
        assert failed.status_code == 401

    blocked = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.test", "password": "correct-horse-battery"},
    )

    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "60"
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert blocked.json()["error"]["details"]["retry_after_seconds"] == 60


async def test_me_uses_the_bearer_token(client: httpx.AsyncClient) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.test", "password": "correct-horse-battery"},
    )
    access_token = login.json()["access_token"]

    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.test"

    anonymous = await client.get("/api/v1/auth/me")
    assert anonymous.status_code == 401
    assert anonymous.headers["www-authenticate"] == "Bearer"
    assert anonymous.json()["error"]["code"] == "authentication_required"

    forged = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalide"},
    )
    assert forged.status_code == 401


async def test_principal_returns_scopes_for_the_resolved_identity(
    client: httpx.AsyncClient,
) -> None:
    from tests.unit.iam.fakes import make_principal

    from workhub.interfaces.rest.dependencies import current_principal

    principal = make_principal(is_admin=False, scopes=frozenset({"skills:read", "tools:read"}))
    app.dependency_overrides[current_principal] = lambda: principal

    response = await client.get(
        "/api/v1/auth/principal",
        headers={"Authorization": "Bearer access"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "id": str(principal.id),
        "type": "user",
        "display_name": "Admin",
        "scopes": ["skills:read", "tools:read"],
    }
