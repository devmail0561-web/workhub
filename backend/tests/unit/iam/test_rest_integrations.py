from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from tests.unit.iam.fakes import (
    FakeApiTokenFactory,
    FakeApiTokenRepository,
    FakeClock,
    FakeIntegrationRepository,
    FakePrincipalResolver,
    make_principal,
)

from workhub.iam.api import Principal, get_integration_service, get_principal_resolver
from workhub.iam.application.integrations import IntegrationService
from workhub.interfaces.rest.app import app
from workhub.interfaces.rest.dependencies import current_principal


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def principal() -> Principal:
    return make_principal()


@pytest.fixture
def service(clock: FakeClock) -> IntegrationService:
    integrations = FakeIntegrationRepository()
    return IntegrationService(
        integrations=integrations,
        tokens=FakeApiTokenRepository(integrations),
        token_factory=FakeApiTokenFactory(),
        clock=clock,
    )


@pytest.fixture
async def client(
    service: IntegrationService,
    principal: Principal,
) -> AsyncIterator[httpx.AsyncClient]:
    async def override_service() -> AsyncIterator[IntegrationService]:
        yield service

    app.dependency_overrides[get_integration_service] = override_service
    app.dependency_overrides[current_principal] = lambda: principal
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def test_integration_lifecycle_exposes_the_token_once(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/integrations",
        json={
            "name": "OpenCode",
            "kind": "opencode",
            "scopes": ["skills:read", "tools:execute"],
        },
    )
    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    body = created.json()
    integration_id = body["integration"]["id"]
    token_id = body["token"]["id"]
    assert body["token"]["token"].startswith("whub_")
    assert body["token"]["scopes"] == ["skills:read", "tools:execute"]

    listed = await client.get("/api/v1/integrations")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [integration_id]

    extra = await client.post(
        f"/api/v1/integrations/{integration_id}/tokens",
        json={"scopes": ["skills:read"]},
    )
    assert extra.status_code == 201
    assert extra.headers["cache-control"] == "no-store"
    assert extra.json()["token"].startswith("whub_")

    revoked_token = await client.delete(f"/api/v1/integrations/{integration_id}/tokens/{token_id}")
    assert revoked_token.status_code == 204

    revoked = await client.delete(f"/api/v1/integrations/{integration_id}")
    assert revoked.status_code == 204

    listed_after = await client.get("/api/v1/integrations")
    assert listed_after.json()[0]["revoked_at"] is not None


async def test_integration_requests_are_validated_and_scoped(
    client: httpx.AsyncClient,
    clock: FakeClock,
) -> None:
    forbidden_scope = await client.post(
        "/api/v1/integrations",
        json={"name": "OpenCode", "kind": "opencode", "scopes": ["integrations:manage"]},
    )
    assert forbidden_scope.status_code == 422
    assert forbidden_scope.json()["error"]["code"] == "validation_error"

    expired = await client.post(
        "/api/v1/integrations",
        json={
            "name": "OpenCode",
            "kind": "opencode",
            "scopes": ["skills:read"],
            "expires_at": (clock.now() - timedelta(seconds=1)).isoformat(),
        },
    )
    assert expired.status_code == 422

    unknown_kind = await client.post(
        "/api/v1/integrations",
        json={"name": "OpenCode", "kind": "inconnu", "scopes": ["skills:read"]},
    )
    assert unknown_kind.status_code == 422


async def test_integration_errors_use_the_common_envelope(
    client: httpx.AsyncClient,
    service: IntegrationService,
    principal: Principal,
) -> None:
    missing = await client.delete(f"/api/v1/integrations/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"

    created = await service.create(
        principal,
        name="OpenCode",
        kind="opencode",
        scopes=["skills:read"],
    )
    await service.revoke(principal, created.integration.id)

    revoked_token = await client.post(
        f"/api/v1/integrations/{created.integration.id}/tokens",
        json={"scopes": ["skills:read"]},
    )
    assert revoked_token.status_code == 409
    assert revoked_token.json()["error"]["code"] == "conflict"


async def test_principal_without_scope_receives_403(
    clock: FakeClock,
) -> None:
    service = IntegrationService(
        integrations=FakeIntegrationRepository(),
        tokens=FakeApiTokenRepository(),
        token_factory=FakeApiTokenFactory(),
        clock=clock,
    )
    principal = make_principal(is_admin=False, scopes=frozenset({"skills:read"}))

    async def override_service() -> AsyncIterator[IntegrationService]:
        yield service

    app.dependency_overrides[get_integration_service] = override_service
    app.dependency_overrides[current_principal] = lambda: principal
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/integrations")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["error"]["details"]["required_scope"] == "integrations:manage"


async def test_anonymous_integration_request_is_rejected(client: httpx.AsyncClient) -> None:
    async def override_resolver() -> AsyncIterator[FakePrincipalResolver]:
        yield FakePrincipalResolver(make_principal())

    app.dependency_overrides.pop(current_principal)
    app.dependency_overrides[get_principal_resolver] = override_resolver
    response = await client.get("/api/v1/integrations")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
