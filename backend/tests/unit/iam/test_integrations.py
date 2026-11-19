from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from tests.unit.iam.fakes import (
    FakeApiTokenFactory,
    FakeApiTokenRepository,
    FakeAuditRecorder,
    FakeClock,
    FakeCommit,
    FakeIntegrationRepository,
    make_principal,
    make_user,
)

from workhub.iam.application.integrations import IntegrationService
from workhub.iam.domain.api_token import API_TOKEN_PREFIX
from workhub.shared.api import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


def build_service() -> tuple[
    IntegrationService,
    FakeIntegrationRepository,
    FakeApiTokenRepository,
    FakeApiTokenFactory,
    FakeClock,
    FakeAuditRecorder,
]:
    clock = FakeClock()
    integrations = FakeIntegrationRepository()
    tokens = FakeApiTokenRepository(integrations)
    factory = FakeApiTokenFactory()
    audit = FakeAuditRecorder()
    service = IntegrationService(
        integrations=integrations,
        tokens=tokens,
        token_factory=factory,
        audit=audit,
        commit=FakeCommit(),
        clock=clock,
    )
    return service, integrations, tokens, factory, clock, audit


async def test_create_returns_the_plaintext_token_only_once() -> None:
    service, integrations, tokens, factory, _, _ = build_service()
    principal = make_principal()

    created = await service.create(
        principal,
        name="  OpenCode  ",
        kind="opencode",
        scopes=["skills:read", "tools:execute"],
    )

    assert created.integration.name == "OpenCode"
    assert created.integration.kind == "opencode"
    assert created.token.token == f"{API_TOKEN_PREFIX}token-1"
    assert created.token.scopes == frozenset({"skills:read", "tools:execute"})
    stored = tokens.tokens[created.token.id]
    assert stored.token_sha256 == factory.hash_token(created.token.token)
    assert created.token.token.encode() not in stored.token_sha256
    assert integrations.integrations[created.integration.id].owner_id == principal.id


async def test_create_rejects_invalid_scopes_kind_and_expiration() -> None:
    service, _, _, _, clock, _ = build_service()
    principal = make_principal()

    with pytest.raises(ValidationError):
        await service.create(principal, name="x", kind="opencode", scopes=[])
    with pytest.raises(ValidationError):
        await service.create(principal, name="x", kind="inconnu", scopes=["skills:read"])
    with pytest.raises(ValidationError):
        await service.create(principal, name=" ", kind="opencode", scopes=["skills:read"])
    with pytest.raises(ValidationError):
        await service.create(principal, name="x", kind="opencode", scopes=["*"])
    with pytest.raises(ValidationError):
        await service.create(
            principal,
            name="x",
            kind="opencode",
            scopes=["integrations:manage"],
        )
    with pytest.raises(ValidationError):
        await service.create(principal, name="x", kind="opencode", scopes=["skills"])
    with pytest.raises(ValidationError):
        await service.create(
            principal,
            name="x",
            kind="opencode",
            scopes=["skills:read"],
            expires_at=clock.now() - timedelta(seconds=1),
        )
    with pytest.raises(ValidationError):
        await service.create(
            principal,
            name="x",
            kind="opencode",
            scopes=["skills:read"],
            expires_at=clock.now().replace(tzinfo=None),
        )


async def test_scopes_require_the_management_permission() -> None:
    service, _, _, _, _, _ = build_service()
    integration_principal = make_principal(
        is_admin=False,
        scopes=frozenset({"skills:read"}),
    )

    with pytest.raises(PermissionDeniedError):
        await service.create(
            integration_principal,
            name="OpenCode",
            kind="opencode",
            scopes=["skills:read"],
        )


async def test_list_is_limited_to_the_owner() -> None:
    service, _, _, _, _, _ = build_service()
    owner = make_principal()
    other = make_principal()

    await service.create(owner, name="A", kind="opencode", scopes=["skills:read"])
    await service.create(other, name="B", kind="codex", scopes=["tools:read"])

    listed = await service.list(owner)
    assert [item.name for item in listed] == ["A"]


async def test_tokens_can_be_added_revoked_and_expire() -> None:
    service, _, tokens, _, clock, _ = build_service()
    principal = make_principal()
    created = await service.create(
        principal,
        name="OpenCode",
        kind="opencode",
        scopes=["skills:read"],
    )

    extra = await service.create_token(
        principal,
        created.integration.id,
        scopes=["tools:execute"],
        expires_at=clock.now() + timedelta(seconds=30),
    )
    assert extra.token.startswith(API_TOKEN_PREFIX)

    await service.revoke_token(principal, created.integration.id, extra.id)
    assert tokens.tokens[extra.id].revoked_at == clock.now()

    await service.revoke(principal, created.integration.id)
    assert tokens.tokens[created.token.id].revoked_at == clock.now()
    with pytest.raises(ConflictError):
        await service.create_token(
            principal,
            created.integration.id,
            scopes=["skills:read"],
        )


async def test_revocation_and_tokens_are_scoped_to_the_owner() -> None:
    service, _, _, _, _, _ = build_service()
    owner = make_principal()
    other = make_principal()
    created = await service.create(
        owner,
        name="OpenCode",
        kind="opencode",
        scopes=["skills:read"],
    )

    with pytest.raises(NotFoundError):
        await service.revoke(other, created.integration.id)
    with pytest.raises(NotFoundError):
        await service.create_token(
            other,
            created.integration.id,
            scopes=["skills:read"],
        )
    with pytest.raises(NotFoundError):
        await service.revoke_token(other, created.integration.id, created.token.id)
    with pytest.raises(NotFoundError):
        await service.revoke_token(owner, created.integration.id, uuid4())


def test_user_view_maps_admins_to_the_wildcard_scope() -> None:
    from workhub.iam.application.views import UserView

    user = make_user()
    assert UserView.from_user(user).to_principal().scopes == frozenset({"*"})
    non_admin = make_user(is_admin=False)
    assert UserView.from_user(non_admin).to_principal().scopes == frozenset()


async def test_writes_are_audited_without_secrets() -> None:
    service, _, _, _, _, audit = build_service()
    principal = make_principal()

    created = await service.create(
        principal,
        name="OpenCode",
        kind="opencode",
        scopes=["skills:read"],
        request_id="req-1",
    )
    await service.create_token(
        principal,
        created.integration.id,
        scopes=["tools:read"],
        request_id="req-2",
    )
    await service.revoke_token(
        principal,
        created.integration.id,
        created.token.id,
        request_id="req-3",
    )
    await service.revoke(principal, created.integration.id, request_id="req-4")

    assert [entry.action for entry in audit.entries] == [
        "integration.create",
        "api_token.create",
        "api_token.revoke",
        "integration.revoke",
    ]
    assert [entry.resource_type for entry in audit.entries] == [
        "integration",
        "api_token",
        "api_token",
        "integration",
    ]
    assert audit.entries[0].request_id == "req-1"
    assert audit.entries[0].details["token_id"] == str(created.token.id)
    assert created.token.token not in repr([entry.details for entry in audit.entries])
