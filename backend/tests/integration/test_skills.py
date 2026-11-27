from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workhub.audit.infrastructure.repositories import SqlAlchemyAuditRecorder
from workhub.iam.application.bootstrap import bootstrap_admin
from workhub.iam.application.integrations import IntegrationService
from workhub.iam.infrastructure.repositories import (
    SqlAlchemyApiTokenRepository,
    SqlAlchemyIntegrationRepository,
    SqlAlchemyUserRepository,
)
from workhub.iam.infrastructure.security import Argon2PasswordHasher, OpaqueApiTokenFactory
from workhub.shared.api import (
    PreconditionFailedError,
    Principal,
    PrincipalType,
    SystemClock,
    ValidationError,
)
from workhub.skills.application.service import SkillService
from workhub.skills.domain.skill import SkillFile
from workhub.skills.infrastructure.repositories import (
    SkillDependencyRow,
    SkillRow,
    SkillVersionRow,
    SqlAlchemySkillRepository,
)

pytestmark = pytest.mark.integration


def _skill_service(session: AsyncSession) -> SkillService:
    return SkillService(
        skills=SqlAlchemySkillRepository(session),
        audit=SqlAlchemyAuditRecorder(session),
        commit=session.commit,
        clock=SystemClock(),
    )


def _integration_service(session: AsyncSession) -> IntegrationService:
    return IntegrationService(
        integrations=SqlAlchemyIntegrationRepository(session),
        tokens=SqlAlchemyApiTokenRepository(session),
        token_factory=OpaqueApiTokenFactory(),
        audit=SqlAlchemyAuditRecorder(session),
        commit=session.commit,
        clock=SystemClock(),
    )


async def _admin(session: AsyncSession) -> Principal:
    user = await bootstrap_admin(
        users=SqlAlchemyUserRepository(session),
        password_hasher=Argon2PasswordHasher(),
        clock=SystemClock(),
        email=f"owner-{uuid4()}@example.test",
        display_name="Ada",
        password="correct-horse-battery",
    )
    await session.commit()
    return user.to_principal()


async def test_integration_owner_origin_etag_and_published_visibility(
    session: AsyncSession,
) -> None:
    owner = await _admin(session)
    slug = f"demo-{uuid4().hex[:8]}"
    skill_md = f"---\nname: {slug}\ndescription: Demo skill\n---\n# Demo\n".encode()
    integrations = _integration_service(session)
    created_integration = await integrations.create(
        owner,
        name="OpenCode",
        kind="opencode",
        scopes=["skills:read", "skills:propose"],
    )
    integration = Principal(
        id=created_integration.integration.id,
        type=PrincipalType.INTEGRATION,
        display_name="OpenCode",
        scopes=frozenset({"skills:read", "skills:propose", "skills:publish"}),
        owner_user_id=owner.id,
    )
    skills = _skill_service(session)

    created = await skills.create(
        integration,
        slug=slug,
        domain="security",
        files=(SkillFile(path="SKILL.md", content=skill_md, mode="755"),),
    )
    row = (
        await session.execute(select(SkillRow).where(SkillRow.id == created.skill.id))
    ).scalar_one()
    assert row.owner_id == owner.id
    assert created.draft.files[0].mode == "0755"

    version = await skills.publish(
        integration,
        slug,
        semver="1.0.0",
        changelog="Initial version",
        expected_lock_version=0,
    )
    version_row = (
        await session.execute(select(SkillVersionRow).where(SkillVersionRow.id == version.id))
    ).scalar_one()
    assert version.origin_kind == "integration"
    assert version.origin_integration_id == integration.id
    assert version_row.origin_kind == "integration"
    assert version_row.origin_integration_id == integration.id

    reader = Principal(
        id=uuid4(),
        type=PrincipalType.INTEGRATION,
        display_name="Reader",
        scopes=frozenset({"skills:read"}),
        owner_user_id=uuid4(),
    )
    assert (await skills.get(reader, slug)).slug == slug
    assert await skills.list_versions(reader, slug)
    assert (await skills.get_version(reader, slug, "1.0.0")).manifest["slug"] == slug

    with pytest.raises(PreconditionFailedError):
        await skills.put_file(
            integration,
            slug,
            path="notes.txt",
            content=b"stale",
            expected_lock_version=0,
        )


async def test_skill_dependencies_are_persisted_and_cycles_rejected(
    session: AsyncSession,
) -> None:
    owner = await _admin(session)
    suffix = uuid4().hex[:8]
    base_slug = f"base-{suffix}"
    demo_slug = f"demo-{suffix}"
    skills = _skill_service(session)
    for slug in (base_slug, demo_slug):
        content = f"---\nname: {slug}\ndescription: Skill {slug}\n---\n".encode()
        await skills.create(
            owner,
            slug=slug,
            domain="security",
            files=(SkillFile(path="SKILL.md", content=content),),
        )
    await skills.publish(owner, base_slug, semver="1.0.0", changelog="base")
    version = await skills.publish(
        owner,
        demo_slug,
        semver="1.0.0",
        changelog="depends on base",
        dependencies=({"slug": base_slug, "constraint": "^1.0.0"},),
    )

    rows = (
        (
            await session.execute(
                select(SkillDependencyRow).where(SkillDependencyRow.version_id == version.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].version_constraint == "^1.0.0"
    detail = await skills.get_version(owner, demo_slug, "1.0.0")
    assert [(item.slug, item.resolved_semver) for item in detail.dependencies] == [
        (base_slug, "1.0.0")
    ]

    with pytest.raises(ValidationError, match="Cycle de dépendances"):
        await skills.publish(
            owner,
            base_slug,
            semver="1.1.0",
            changelog="would create a cycle",
            dependencies=({"slug": demo_slug, "constraint": "^1.0.0"},),
        )
