from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from tests.unit.iam.fakes import (
    FakeApiTokenFactory,
    FakeApiTokenRepository,
    FakeClock,
    FakeIntegrationRepository,
    FakeTokenIssuer,
    FakeUserRepository,
    make_integration,
    make_user,
)

from workhub.iam.application.principal import PrincipalResolver
from workhub.iam.domain.api_token import ApiToken
from workhub.shared.api import AuthenticationError, PrincipalType


def build_resolver(
    *,
    users: FakeUserRepository,
    integrations: FakeIntegrationRepository,
    tokens: FakeApiTokenRepository,
    clock: FakeClock,
    factory: FakeApiTokenFactory,
) -> PrincipalResolver:
    return PrincipalResolver(
        users=users,
        tokens=tokens,
        token_issuer=FakeTokenIssuer(),
        token_factory=factory,
        clock=clock,
    )


def _api_token_setup(
    *,
    scopes: frozenset[str] = frozenset({"skills:read"}),
    expires_delta: int | None = None,
) -> tuple[
    PrincipalResolver,
    FakeApiTokenRepository,
    FakeClock,
    FakeApiTokenFactory,
    str,
]:
    clock = FakeClock()
    user = make_user()
    integrations = FakeIntegrationRepository()
    integration = make_integration(owner_id=user.id, clock=clock)
    integrations.integrations[integration.id] = integration
    tokens = FakeApiTokenRepository(integrations)
    factory = FakeApiTokenFactory()
    raw, token_hash = factory.new_token()
    expires_at = None if expires_delta is None else clock.now() + timedelta(seconds=expires_delta)
    token = ApiToken(
        id=uuid4(),
        integration_id=integration.id,
        token_sha256=token_hash,
        scopes=scopes,
        created_at=clock.now(),
        expires_at=expires_at,
    )
    tokens.tokens[token.id] = token
    resolver = build_resolver(
        users=FakeUserRepository(),
        integrations=integrations,
        tokens=tokens,
        clock=clock,
        factory=factory,
    )
    return resolver, tokens, clock, factory, raw


async def test_resolves_an_active_user_access_token() -> None:
    clock = FakeClock()
    users = FakeUserRepository()
    user = make_user()
    users.users[user.id] = user
    resolver = build_resolver(
        users=users,
        integrations=FakeIntegrationRepository(),
        tokens=FakeApiTokenRepository(),
        clock=clock,
        factory=FakeApiTokenFactory(),
    )
    access = FakeTokenIssuer().issue_access_token(user.id, clock.now(), 900)

    principal = await resolver.resolve(access.value)

    assert principal.id == user.id
    assert principal.type is PrincipalType.USER
    assert principal.scopes == frozenset({"*"})


async def test_rejects_inactive_or_unknown_users_and_forged_tokens() -> None:
    clock = FakeClock()
    users = FakeUserRepository()
    inactive = make_user(is_active=False)
    users.users[inactive.id] = inactive
    resolver = build_resolver(
        users=users,
        integrations=FakeIntegrationRepository(),
        tokens=FakeApiTokenRepository(),
        clock=clock,
        factory=FakeApiTokenFactory(),
    )
    access = FakeTokenIssuer().issue_access_token(inactive.id, clock.now(), 900)

    with pytest.raises(AuthenticationError):
        await resolver.resolve(access.value)
    with pytest.raises(AuthenticationError):
        await resolver.resolve("invalide")


async def test_resolves_an_api_token_and_updates_last_used() -> None:
    resolver, tokens, clock, _, raw = _api_token_setup()

    principal = await resolver.resolve(raw)

    assert principal.type is PrincipalType.INTEGRATION
    assert principal.display_name == "OpenCode"
    assert principal.scopes == frozenset({"skills:read"})
    stored = next(iter(tokens.tokens.values()))
    assert stored.last_used_at == clock.now()
    assert principal.id == stored.integration_id


async def test_api_token_expiration_revocation_and_unknown_hash_are_rejected() -> None:
    resolver, tokens, clock, factory, raw = _api_token_setup(expires_delta=30)
    token = next(iter(tokens.tokens.values()))
    clock.advance(30)
    with pytest.raises(AuthenticationError):
        await resolver.resolve(raw)

    token = next(iter(tokens.tokens.values()))
    tokens.tokens[token.id] = ApiToken(
        id=token.id,
        integration_id=token.integration_id,
        token_sha256=token.token_sha256,
        scopes=token.scopes,
        created_at=token.created_at,
        revoked_at=clock.now(),
    )
    with pytest.raises(AuthenticationError):
        await resolver.resolve(raw)
    with pytest.raises(AuthenticationError):
        await resolver.resolve(f"{factory.new_token()[0]}")
