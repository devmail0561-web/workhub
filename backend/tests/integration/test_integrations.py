from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from workhub.audit.infrastructure.repositories import SqlAlchemyAuditRecorder
from workhub.iam.application.bootstrap import bootstrap_admin
from workhub.iam.application.integrations import IntegrationService
from workhub.iam.application.principal import PrincipalResolver
from workhub.iam.domain.api_token import API_TOKEN_PREFIX
from workhub.iam.infrastructure.repositories import (
    ApiTokenRow,
    AppUserRow,
    SqlAlchemyApiTokenRepository,
    SqlAlchemyIntegrationRepository,
    SqlAlchemyUserRepository,
)
from workhub.iam.infrastructure.security import (
    Argon2PasswordHasher,
    JwtTokenIssuer,
    OpaqueApiTokenFactory,
)
from workhub.shared.api import (
    AuthenticationError,
    NotFoundError,
    PrincipalType,
    SystemClock,
)

pytestmark = pytest.mark.integration

SECRET = "test-secret-key-0123456789abcdef"


def _services(
    session: AsyncSession,
) -> tuple[IntegrationService, PrincipalResolver]:
    integrations = SqlAlchemyIntegrationRepository(session)
    tokens = SqlAlchemyApiTokenRepository(session)
    factory = OpaqueApiTokenFactory()
    clock = SystemClock()
    return (
        IntegrationService(
            integrations=integrations,
            tokens=tokens,
            token_factory=factory,
            audit=SqlAlchemyAuditRecorder(session),
            commit=session.commit,
            clock=clock,
        ),
        PrincipalResolver(
            users=SqlAlchemyUserRepository(session),
            tokens=tokens,
            token_issuer=JwtTokenIssuer(SECRET),
            token_factory=factory,
            commit=session.commit,
            clock=clock,
        ),
    )


async def test_integration_token_is_hashed_resolved_and_revoked(
    session: AsyncSession,
) -> None:
    admin = await bootstrap_admin(
        users=SqlAlchemyUserRepository(session),
        password_hasher=Argon2PasswordHasher(),
        clock=SystemClock(),
        email=f"owner-{uuid4()}@example.test",
        display_name="Ada",
        password="correct-horse-battery",
    )
    await session.commit()
    service, resolver = _services(session)

    created = await service.create(
        admin.to_principal(),
        name="OpenCode",
        kind="opencode",
        scopes=["skills:read", "tools:execute"],
    )
    await session.commit()

    assert created.token.token.startswith(API_TOKEN_PREFIX)
    row = (
        await session.execute(select(ApiTokenRow).where(ApiTokenRow.id == created.token.id))
    ).scalar_one()
    assert row.token_sha256 == OpaqueApiTokenFactory().hash_token(created.token.token)
    assert row.scopes == ["skills:read", "tools:execute"]
    assert created.token.token.encode() not in row.token_sha256

    principal = await resolver.resolve(created.token.token)
    await session.commit()
    assert principal.type is PrincipalType.INTEGRATION
    assert principal.id == created.integration.id
    assert principal.scopes == frozenset({"skills:read", "tools:execute"})

    await session.refresh(row)
    assert row.last_used_at is not None

    await service.revoke_token(
        admin.to_principal(),
        created.integration.id,
        created.token.id,
    )
    await session.commit()
    with pytest.raises(AuthenticationError):
        await resolver.resolve(created.token.token)

    await service.revoke(admin.to_principal(), created.integration.id)
    await session.commit()


async def test_expiration_and_owner_isolation(session: AsyncSession) -> None:
    owner = await bootstrap_admin(
        users=SqlAlchemyUserRepository(session),
        password_hasher=Argon2PasswordHasher(),
        clock=SystemClock(),
        email=f"owner-{uuid4()}@example.test",
        display_name="Ada",
        password="correct-horse-battery",
    )
    other = await bootstrap_admin(
        users=SqlAlchemyUserRepository(session),
        password_hasher=Argon2PasswordHasher(),
        clock=SystemClock(),
        email=f"other-{uuid4()}@example.test",
        display_name="Grace",
        password="correct-horse-battery",
    )
    await session.commit()
    service, resolver = _services(session)

    created = await service.create(
        owner.to_principal(),
        name="Claude",
        kind="claude_code",
        scopes=["skills:read"],
        expires_at=SystemClock().now() + timedelta(seconds=60),
    )
    await session.commit()

    assert await service.list(owner.to_principal())
    assert await service.list(other.to_principal()) == []
    with pytest.raises(NotFoundError):
        await service.revoke(other.to_principal(), created.integration.id)
    with pytest.raises(NotFoundError):
        await service.create_token(
            other.to_principal(),
            created.integration.id,
            scopes=["skills:read"],
        )

    await session.execute(
        text(
            "update api_token set created_at = now() - interval '2 minutes', "
            "expires_at = now() - interval '1 minute' where id = :id"
        ),
        {"id": created.token.id},
    )
    await session.commit()
    with pytest.raises(AuthenticationError):
        await resolver.resolve(created.token.token)


async def test_schema_guards_reject_invalid_kinds_and_expirations(
    session: AsyncSession,
) -> None:
    owner = await bootstrap_admin(
        users=SqlAlchemyUserRepository(session),
        password_hasher=Argon2PasswordHasher(),
        clock=SystemClock(),
        email=f"guard-{uuid4()}@example.test",
        display_name="Ada",
        password="correct-horse-battery",
    )
    await session.commit()

    with pytest.raises(IntegrityError):
        await session.execute(
            text(
                "insert into integration (name, kind, owner_id) values ('x', 'inconnu', :owner_id)"
            ),
            {"owner_id": owner.id},
        )
    await session.rollback()

    integration_id = uuid4()
    await session.execute(
        text(
            "insert into integration (id, name, kind, owner_id) "
            "values (:id, 'x', 'opencode', :owner_id)"
        ),
        {"id": integration_id, "owner_id": owner.id},
    )
    await session.commit()

    with pytest.raises(IntegrityError):
        await session.execute(
            text(
                "insert into api_token (integration_id, token_sha256, scopes, created_at, "
                "expires_at) values (:integration_id, digest('a', 'sha256'), "
                "array['skills:read'], now(), now())"
            ),
            {"integration_id": integration_id},
        )
    await session.rollback()


async def test_owner_deactivation_invalidates_existing_tokens(session: AsyncSession) -> None:
    owner = await bootstrap_admin(
        users=SqlAlchemyUserRepository(session),
        password_hasher=Argon2PasswordHasher(),
        clock=SystemClock(),
        email=f"disabled-{uuid4()}@example.test",
        display_name="Ada",
        password="correct-horse-battery",
    )
    await session.commit()
    service, resolver = _services(session)
    created = await service.create(
        owner.to_principal(),
        name="OpenCode",
        kind="opencode",
        scopes=["skills:read"],
    )

    await session.execute(
        update(AppUserRow).where(AppUserRow.id == owner.id).values(is_active=False)
    )
    await session.commit()

    with pytest.raises(AuthenticationError):
        await resolver.resolve(created.token.token)


async def test_integration_writes_are_audited(session: AsyncSession) -> None:
    owner = await bootstrap_admin(
        users=SqlAlchemyUserRepository(session),
        password_hasher=Argon2PasswordHasher(),
        clock=SystemClock(),
        email=f"audit-{uuid4()}@example.test",
        display_name="Ada",
        password="correct-horse-battery",
    )
    await session.commit()
    service, _ = _services(session)
    request_id = f"req-{uuid4()}"

    created = await service.create(
        owner.to_principal(),
        name="OpenCode",
        kind="opencode",
        scopes=["skills:read"],
        request_id=request_id,
    )
    await service.revoke(
        owner.to_principal(),
        created.integration.id,
        request_id=request_id,
    )

    rows = (
        await session.execute(
            text(
                "select action, resource_type, resource_id, request_id, principal_id "
                "from audit_log where request_id = :request_id order by id"
            ),
            {"request_id": request_id},
        )
    ).all()
    assert [row.action for row in rows] == ["integration.create", "integration.revoke"]
    assert [row.resource_type for row in rows] == ["integration", "integration"]
    assert rows[0].resource_id == str(created.integration.id)
    assert rows[0].principal_id == owner.id
    assert created.token.token not in repr(rows)
