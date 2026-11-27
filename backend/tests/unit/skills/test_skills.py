from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from typing import cast
from uuid import uuid4

import httpx
import pytest
from tests.unit.iam.fakes import FakeAuditRecorder, FakeClock, FakeCommit, make_principal
from tests.unit.skills.fakes import FakeSkillRepository

import workhub.skills.application.service as skills_service_module
from workhub.interfaces.rest.app import app
from workhub.interfaces.rest.dependencies import current_principal
from workhub.shared.api import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    PreconditionFailedError,
    Principal,
    PrincipalType,
    ValidationError,
)
from workhub.skills.api import SkillService, get_skill_service
from workhub.skills.domain.skill import (
    SkillFile,
    build_manifest,
    diff_files,
    manifest_sha256,
    normalize_dependencies,
    normalize_requirements,
    satisfies_constraint,
    semver_key,
    summarize_diff,
    validate_constraint,
    validate_files,
    validate_mode,
    validate_path,
    validate_semver,
)

SKILL_MD = b"---\nname: demo-skill\ndescription: Demo skill\n---\n# Demo\n"


def build_service() -> tuple[SkillService, FakeSkillRepository, FakeAuditRecorder]:
    repository = FakeSkillRepository()
    audit = FakeAuditRecorder()
    service = SkillService(
        skills=repository,
        audit=audit,
        commit=FakeCommit(),
        clock=FakeClock(),
    )
    return service, repository, audit


async def create_demo(service: SkillService, principal: Principal | None = None) -> None:
    await service.create(
        principal or make_principal(),
        slug="demo-skill",
        domain="security",
        files=(SkillFile(path="SKILL.md", content=SKILL_MD),),
    )


async def create_named(service: SkillService, principal: Principal, slug: str) -> None:
    content = f"---\nname: {slug}\ndescription: Skill {slug}\n---\n".encode()
    await service.create(
        principal,
        slug=slug,
        domain="security",
        files=(SkillFile(path="SKILL.md", content=content),),
    )


def test_manifest_is_deterministic_and_depends_on_content() -> None:
    first = SkillFile(path="b.txt", content=b"b")
    second = SkillFile(path="a.txt", content=b"a")
    skill_md = SkillFile(path="SKILL.md", content=SKILL_MD)
    manifest = build_manifest(
        slug="demo-skill",
        name="demo-skill",
        description="Demo skill",
        semver="1.0.0",
        parent=None,
        files=(first, second, skill_md),
    )
    reversed_manifest = build_manifest(
        slug="demo-skill",
        name="demo-skill",
        description="Demo skill",
        semver="1.0.0",
        parent=None,
        files=(skill_md, second, first),
    )

    assert manifest["manifest_version"] == 1
    assert manifest["name"] == "demo-skill"
    assert manifest["description"] == "Demo skill"
    assert manifest["files"] == reversed_manifest["files"]
    assert manifest_sha256(manifest) == manifest_sha256(reversed_manifest)
    changed = build_manifest(
        slug="demo-skill",
        name="demo-skill",
        description="Demo skill",
        semver="1.0.0",
        parent=None,
        files=(SkillFile(path="a.txt", content=b"changed"), second, skill_md),
    )
    assert manifest_sha256(changed) != manifest_sha256(manifest)


def test_manifest_includes_canonical_requirements() -> None:
    requirement: dict[str, object] = {
        "kind": "package",
        "ecosystem": "pypi",
        "name": "python-nmap",
    }
    other: dict[str, object] = {
        "kind": "system",
        "name": "nmap",
        "usage": "optional",
    }
    manifest = build_manifest(
        slug="demo-skill",
        name="demo-skill",
        description="Demo skill",
        semver="1.0.0",
        parent=None,
        files=(SkillFile(path="SKILL.md", content=SKILL_MD),),
        requirements=(other, requirement),
    )
    assert manifest["requirements"] == [
        {**requirement, "usage": "required"},
        other,
    ]
    reversed_manifest = build_manifest(
        slug="demo-skill",
        name="demo-skill",
        description="Demo skill",
        semver="1.0.0",
        parent=None,
        files=(SkillFile(path="SKILL.md", content=SKILL_MD),),
        requirements=(requirement, other),
    )
    assert manifest_sha256(manifest) == manifest_sha256(reversed_manifest)


def test_requirements_are_validated_and_hashes_are_supported() -> None:
    requirement = normalize_requirements(
        (
            {
                "kind": "script",
                "tool_version_id": str(uuid4()),
                "hashes": {"sha256": "abc"},
            },
        )
    )
    assert requirement[0]["kind"] == "script"
    assert requirement[0]["hashes"] == {"sha256": "abc"}
    with pytest.raises(ValidationError):
        normalize_requirements(({"kind": "bogus"},))
    with pytest.raises(ValidationError):
        normalize_requirements(({"kind": "package", "name": "x"},))
    with pytest.raises(ValidationError):
        normalize_requirements(({"kind": "system"},))


def test_file_and_frontmatter_validation_rejects_unsafe_input() -> None:
    for path in ("../secret", "/absolute", ".", "./SKILL.md", "a//b", "a\x00b", "a/../b"):
        with pytest.raises(ValidationError):
            validate_path(path)
    for semver in ("1.0", "1.0.0-.", "1.0.0-alpha..1", "1.0.0-01"):
        with pytest.raises(ValidationError):
            validate_semver(semver)
    assert validate_mode("755") == "0755"
    with pytest.raises(ValidationError):
        validate_mode("888")
    with pytest.raises(ValidationError):
        validate_files((SkillFile(path="README.md", content=b"x"),), slug="demo")
    with pytest.raises(ValidationError):
        validate_files(
            (SkillFile(path="SKILL.md", content=b"---\nname: autre\ndescription: x\n---\n"),),
            slug="demo",
        )
    with pytest.raises(ValidationError):
        validate_files(
            (SkillFile(path="SKILL.md", content=b"---\nname: demo\n---\n"),),
            slug="demo",
        )


def test_semver_ordering() -> None:
    assert semver_key("1.0.0") < semver_key("1.1.0")
    assert semver_key("1.0.0-alpha") < semver_key("1.0.0")
    assert semver_key("2.0.0") > semver_key("1.99.99")
    assert semver_key("1.0.0-2") < semver_key("1.0.0-10")
    assert semver_key("1.0.0-alpha.2") < semver_key("1.0.0-alpha.10")
    assert semver_key("1.0.0-alpha.10") < semver_key("1.0.0-alpha.beta")


def test_semver_constraints_are_validated_and_evaluated() -> None:
    assert validate_constraint(" >=1.0.0   <2.0.0 ") == ">=1.0.0 <2.0.0"
    assert satisfies_constraint("1.5.0", "^1.2.0")
    assert not satisfies_constraint("2.0.0", "^1.2.0")
    assert satisfies_constraint("0.2.5", "^0.2.3")
    assert not satisfies_constraint("0.3.0", "^0.2.3")
    assert satisfies_constraint("0.0.3", "^0.0.3")
    assert not satisfies_constraint("0.0.4", "^0.0.3")
    assert satisfies_constraint("1.2.9", "~1.2.3")
    assert not satisfies_constraint("1.3.0", "~1.2.3")
    assert satisfies_constraint("1.4.0", ">=1.0.0 <2.0.0")
    assert not satisfies_constraint("2.0.0", ">=1.0.0 <2.0.0")
    assert satisfies_constraint("3.0.0", "1.x || 3.x")
    assert not satisfies_constraint("2.0.0", "1.x || 3.x")
    assert satisfies_constraint("1.2.7", "1.2.x")
    assert not satisfies_constraint("1.3.0", "1.2.x")
    assert satisfies_constraint("4.0.0", "*")

    for invalid in ("", ">=1.0.0 ||", "nope", "^", "1.0.0-", "1.x.3", ">= 1.0.0 <"):
        with pytest.raises(ValidationError):
            validate_constraint(invalid)


def test_dependencies_are_normalized_and_deduplicated() -> None:
    dependencies = normalize_dependencies(
        (
            {"slug": "base-skill", "constraint": " ^1.0.0 "},
            {"slug": "audit-skill", "constraint": "~2.1.0"},
        )
    )
    assert [(item.slug, item.constraint) for item in dependencies] == [
        ("audit-skill", "~2.1.0"),
        ("base-skill", "^1.0.0"),
    ]
    with pytest.raises(ValidationError):
        normalize_dependencies(
            (
                {"slug": "base-skill", "constraint": "^1.0.0"},
                {"slug": "base-skill", "constraint": "^2.0.0"},
            )
        )
    with pytest.raises(ValidationError):
        normalize_dependencies(({"slug": "base-skill", "constraint": "^1.0.0", "x": 1},))
    with pytest.raises(ValidationError):
        normalize_dependencies(({"slug": "Base Skill", "constraint": "^1.0.0"},))


def test_diff_files_reports_changes_and_handles_binary_content() -> None:
    before = (
        SkillFile(path="SKILL.md", content=SKILL_MD),
        SkillFile(path="old.txt", content=b"old\n"),
        SkillFile(path="same.txt", content=b"same\n"),
        SkillFile(path="run.sh", content=b"#!/bin/sh\n", mode="0644"),
    )
    after = (
        SkillFile(path="SKILL.md", content=SKILL_MD + b"# Demo v2\n"),
        SkillFile(path="new.txt", content=b"new\n"),
        SkillFile(path="same.txt", content=b"same\n"),
        SkillFile(path="run.sh", content=b"#!/bin/sh\n", mode="0755"),
        SkillFile(path="logo.png", content=b"\x89PNG\x00\x01"),
    )

    by_path = {diff.path: diff for diff in diff_files(before, after)}

    assert set(by_path) == {"SKILL.md", "new.txt", "old.txt", "run.sh", "logo.png"}
    assert by_path["new.txt"].change == "added"
    assert by_path["old.txt"].change == "deleted"
    assert by_path["SKILL.md"].change == "modified"
    assert by_path["SKILL.md"].text is not None
    assert "+# Demo v2" in by_path["SKILL.md"].text
    assert by_path["run.sh"].change == "modified"
    assert by_path["run.sh"].text == ""
    assert by_path["logo.png"].binary is True
    assert by_path["logo.png"].text is None


async def test_diff_between_published_versions() -> None:
    service, _, _ = build_service()
    principal = make_principal()
    await create_demo(service, principal)
    await service.publish(principal, "demo-skill", semver="1.0.0", changelog="v1")
    await service.put_file(
        principal,
        "demo-skill",
        path="notes.txt",
        content=b"hello\n",
        expected_lock_version=1,
    )
    await service.publish(principal, "demo-skill", semver="1.1.0", changelog="v2")

    diff = await service.diff(
        principal,
        "demo-skill",
        from_semver="1.0.0",
        to_semver="1.1.0",
    )

    assert diff.slug == "demo-skill"
    assert diff.from_semver == "1.0.0"
    assert diff.to_semver == "1.1.0"
    assert [(item.path, item.change) for item in diff.files] == [("notes.txt", "added")]
    assert diff.files[0].text is not None
    assert "+hello" in diff.files[0].text

    with pytest.raises(NotFoundError):
        await service.diff(principal, "demo-skill", from_semver="9.9.9", to_semver="1.1.0")
    with pytest.raises(ValidationError):
        await service.diff(principal, "demo-skill", from_semver="bad", to_semver="1.1.0")


def test_diff_stats_summarize_a_change_like_git_log() -> None:
    before = (SkillFile(path="a.txt", content=b"one\ntwo\n"),)
    after = (
        SkillFile(path="a.txt", content=b"one\nthree\n"),
        SkillFile(path="b.txt", content=b"new\n"),
    )

    stats = summarize_diff(diff_files(before, after))

    assert stats.files_added == 1
    assert stats.files_modified == 1
    assert stats.files_deleted == 0
    assert stats.insertions == 2
    assert stats.deletions == 1


async def test_version_history_keeps_previous_versions_readable() -> None:
    service, _, _ = build_service()
    principal = make_principal()
    await create_demo(service, principal)
    await service.publish(principal, "demo-skill", semver="1.0.0", changelog="Initial")
    await service.put_file(
        principal,
        "demo-skill",
        path="notes.txt",
        content=b"hello\n",
        expected_lock_version=1,
    )
    await service.publish(principal, "demo-skill", semver="1.1.0", changelog="Add notes")

    history = await service.history(principal, "demo-skill")

    assert history.slug == "demo-skill"
    assert history.head == "1.1.0"
    assert [entry.semver for entry in history.versions] == ["1.1.0", "1.0.0"]
    latest, first = history.versions
    assert latest.parent_semver == "1.0.0"
    assert latest.changelog == "Add notes"
    assert latest.changes.files_added == 1
    assert latest.changes.files_modified == 0
    assert latest.changes.insertions == 1
    assert first.parent_semver is None
    assert first.changes.files_added == 1

    previous = await service.get_version(principal, "demo-skill", "1.0.0")
    assert previous.version.status == "published"
    assert previous.version.semver == "1.0.0"


async def test_create_and_publish_build_an_immutable_version() -> None:
    service, repository, audit = build_service()
    principal = make_principal()

    created = await service.create(
        principal,
        slug="demo-skill",
        domain="security",
        files=(SkillFile(path="SKILL.md", content=SKILL_MD),),
    )
    assert created.skill.status == "draft"
    assert created.draft.files[0].path == "SKILL.md"

    version = await service.publish(
        principal,
        "demo-skill",
        semver="1.0.0",
        changelog="Initial version",
        requirements=({"kind": "package", "ecosystem": "pypi", "name": "python-nmap"},),
        request_id="req-1",
    )

    assert version.semver == "1.0.0"
    assert version.status == "published"
    assert version.parent_semver is None
    assert repository.skills[created.skill.id].status == "published"
    assert repository.requirements[version.id][0]["name"] == "python-nmap"
    assert version.origin_kind == "app"
    assert version.origin_integration_id is None
    assert [entry.action for entry in audit.entries] == ["skill.create", "skill.publish"]

    detail = await service.get_version(principal, "demo-skill", "1.0.0")
    assert detail.files[0].path == "SKILL.md"
    assert detail.manifest["slug"] == "demo-skill"
    assert detail.manifest["name"] == "demo-skill"
    assert detail.manifest["description"] == "Demo skill"
    assert detail.manifest["manifest_version"] == 1


async def test_publish_accepts_script_requirements_and_rejects_invalid_ones() -> None:
    service, _, _ = build_service()
    principal = make_principal()
    await create_demo(service, principal)

    version = await service.publish(
        principal,
        "demo-skill",
        semver="1.0.0",
        changelog="v1",
        requirements=(
            {
                "kind": "script",
                "tool_version_id": str(uuid4()),
                "hashes": {"sha256": "abc"},
            },
        ),
    )
    detail = await service.get_version(principal, "demo-skill", "1.0.0")
    requirements = cast("list[object]", detail.manifest["requirements"])
    assert isinstance(requirements, list)
    requirement = requirements[0]
    assert isinstance(requirement, dict)
    assert requirement["kind"] == "script"
    assert requirement["usage"] == "required"
    assert requirement["hashes"] == {"sha256": "abc"}
    assert requirement["tool_version_id"]
    assert version.origin_kind == "app"

    with pytest.raises(ValidationError):
        await service.publish(
            principal,
            "demo-skill",
            semver="1.0.1",
            changelog="invalid",
            requirements=({"kind": "bogus"},),
        )


async def test_publish_requires_a_strictly_increasing_version() -> None:
    service, _, _ = build_service()
    principal = make_principal()
    await create_demo(service, principal)

    await service.publish(principal, "demo-skill", semver="1.0.0", changelog="v1")
    await service.publish(principal, "demo-skill", semver="1.1.0", changelog="v1.1")

    with pytest.raises(ConflictError):
        await service.publish(principal, "demo-skill", semver="1.0.0", changelog="duplicate")
    with pytest.raises(ConflictError):
        await service.publish(principal, "demo-skill", semver="1.0.5", changelog="lower")


async def test_publish_resolves_dependencies_to_the_highest_matching_version() -> None:
    service, repository, _ = build_service()
    principal = make_principal()
    await create_named(service, principal, "base-skill")
    await service.publish(principal, "base-skill", semver="1.0.0", changelog="base v1")
    await service.publish(principal, "base-skill", semver="1.2.0", changelog="base v1.2")
    await service.publish(principal, "base-skill", semver="2.0.0", changelog="base v2")
    await create_demo(service, principal)

    version = await service.publish(
        principal,
        "demo-skill",
        semver="1.0.0",
        changelog="uses base",
        dependencies=({"slug": "base-skill", "constraint": "^1.0.0"},),
    )

    detail = await service.get_version(principal, "demo-skill", "1.0.0")
    assert [(item.slug, item.constraint, item.resolved_semver) for item in detail.dependencies] == [
        ("base-skill", "^1.0.0", "1.2.0")
    ]
    assert detail.manifest["dependencies"] == [
        {
            "slug": "base-skill",
            "constraint": "^1.0.0",
            "resolved_semver": "1.2.0",
        }
    ]
    stored = repository.dependencies[version.id]
    assert [(item.slug, item.constraint, item.semver) for item in stored] == [
        ("base-skill", "^1.0.0", "1.2.0")
    ]


async def test_publish_rejects_unknown_unsatisfied_or_self_dependencies() -> None:
    service, _, _ = build_service()
    principal = make_principal()
    await create_named(service, principal, "base-skill")
    await service.publish(principal, "base-skill", semver="1.0.0", changelog="base v1")
    await create_demo(service, principal)

    with pytest.raises(ValidationError):
        await service.publish(
            principal,
            "demo-skill",
            semver="1.0.0",
            changelog="unknown",
            dependencies=({"slug": "missing-skill", "constraint": "^1.0.0"},),
        )
    with pytest.raises(ConflictError):
        await service.publish(
            principal,
            "demo-skill",
            semver="1.0.0",
            changelog="unsatisfied",
            dependencies=({"slug": "base-skill", "constraint": "^9.0.0"},),
        )
    with pytest.raises(ValidationError):
        await service.publish(
            principal,
            "demo-skill",
            semver="1.0.0",
            changelog="self",
            dependencies=({"slug": "demo-skill", "constraint": "^1.0.0"},),
        )


async def test_publish_rejects_dependency_cycles() -> None:
    service, _, _ = build_service()
    principal = make_principal()
    await create_named(service, principal, "base-skill")
    await service.publish(principal, "base-skill", semver="1.0.0", changelog="base v1")
    await create_demo(service, principal)
    await service.publish(
        principal,
        "demo-skill",
        semver="1.0.0",
        changelog="depends on base",
        dependencies=({"slug": "base-skill", "constraint": "^1.0.0"},),
    )

    with pytest.raises(ValidationError, match="Cycle de dépendances"):
        await service.publish(
            principal,
            "base-skill",
            semver="1.1.0",
            changelog="would create a cycle",
            dependencies=({"slug": "demo-skill", "constraint": "^1.0.0"},),
        )


async def test_create_rejects_duplicates_and_invalid_files() -> None:
    service, _, _ = build_service()
    principal = make_principal()
    await create_demo(service, principal)

    with pytest.raises(ConflictError):
        await create_demo(service, principal)
    with pytest.raises(ValidationError):
        await service.create(
            principal,
            slug="other",
            domain="security",
            files=(SkillFile(path="README.md", content=b"x"),),
        )


async def test_draft_file_crud_and_ownership() -> None:
    service, repository, audit = build_service()
    owner = make_principal()
    other = make_principal(is_admin=False, scopes=frozenset({"skills:read"}))
    await create_demo(service, owner)

    updated = await service.put_file(
        owner,
        "demo-skill",
        path="notes/readme.md",
        content=b"notes",
        expected_lock_version=0,
        request_id="req-put",
    )
    assert updated.lock_version == 1
    assert {file.path for file in updated.files} == {"SKILL.md", "notes/readme.md"}
    assert await repository.read_blob(updated.files[1].sha256) == b"notes"

    with pytest.raises(PreconditionFailedError):
        await service.put_file(
            owner,
            "demo-skill",
            path="notes/readme.md",
            content=b"stale",
            expected_lock_version=0,
        )

    removed = await service.delete_file(
        owner,
        "demo-skill",
        path="notes/readme.md",
        expected_lock_version=1,
    )
    assert removed.lock_version == 2
    assert [file.path for file in removed.files] == ["SKILL.md"]
    with pytest.raises(ValidationError):
        await service.delete_file(owner, "demo-skill", path="SKILL.md", expected_lock_version=2)
    with pytest.raises(NotFoundError):
        await service.get(other, "demo-skill")
    with pytest.raises(NotFoundError):
        await service.get(owner, "inconnue")
    assert [entry.action for entry in audit.entries][-2:] == [
        "skill.draft.file.put",
        "skill.draft.file.delete",
    ]


async def test_permissions_are_checked_by_the_application_layer() -> None:
    service, _, _ = build_service()
    reader = make_principal(is_admin=False, scopes=frozenset({"skills:read"}))
    proposer = make_principal(is_admin=False, scopes=frozenset({"skills:propose"}))
    await create_demo(service, proposer)

    with pytest.raises(PermissionDeniedError):
        await service.create(
            reader,
            slug="autre",
            domain="x",
            files=(SkillFile(path="SKILL.md", content=SKILL_MD.replace(b"demo-skill", b"autre")),),
        )
    with pytest.raises(PermissionDeniedError):
        await service.publish(proposer, "demo-skill", semver="1.0.0", changelog="x")


async def test_integration_creates_for_owner_and_records_origin() -> None:
    service, repository, _ = build_service()
    owner = make_principal()
    integration = Principal(
        id=uuid4(),
        type=PrincipalType.INTEGRATION,
        display_name="OpenCode",
        scopes=frozenset({"skills:read", "skills:propose", "skills:publish"}),
        owner_user_id=owner.id,
    )

    created = await service.create(
        integration,
        slug="demo-skill",
        domain="security",
        files=(SkillFile(path="SKILL.md", content=SKILL_MD),),
    )
    assert repository.skills[created.skill.id].owner_id == owner.id

    version = await service.publish(
        integration,
        "demo-skill",
        semver="1.0.0",
        changelog="Initial version",
    )
    assert version.origin_kind == "integration"
    assert version.origin_integration_id == integration.id


async def test_put_file_enforces_total_draft_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, _ = build_service()
    principal = make_principal()
    await create_demo(service, principal)
    monkeypatch.setattr(skills_service_module, "MAX_VERSION_BYTES", len(SKILL_MD))

    with pytest.raises(ValidationError):
        await service.put_file(
            principal,
            "demo-skill",
            path="notes.txt",
            content=b"x",
            expected_lock_version=0,
        )


async def test_published_skills_are_readable_by_other_integrations_but_drafts_are_not() -> None:
    service, _, _ = build_service()
    owner = make_principal()
    reader = Principal(
        id=uuid4(),
        type=PrincipalType.INTEGRATION,
        display_name="Reader",
        scopes=frozenset({"skills:read"}),
        owner_user_id=uuid4(),
    )
    await create_demo(service, owner)

    with pytest.raises(NotFoundError):
        await service.get(reader, "demo-skill")

    await service.publish(owner, "demo-skill", semver="1.0.0", changelog="v1")

    assert (await service.get(reader, "demo-skill")).slug == "demo-skill"
    assert len(await service.list_versions(reader, "demo-skill")) == 1
    detail = await service.get_version(reader, "demo-skill", "1.0.0")
    assert detail.manifest["slug"] == "demo-skill"
    assert [skill.slug for skill in await service.list(reader)] == ["demo-skill"]
    with pytest.raises(NotFoundError):
        await service.get_draft(reader, "demo-skill")


async def test_publish_requires_matching_draft_version() -> None:
    service, _, _ = build_service()
    principal = make_principal()
    await create_demo(service, principal)

    await service.publish(
        principal,
        "demo-skill",
        semver="1.0.0",
        changelog="v1",
        expected_lock_version=0,
    )
    with pytest.raises(PreconditionFailedError):
        await service.publish(
            principal,
            "demo-skill",
            semver="1.0.1",
            changelog="stale",
            expected_lock_version=0,
        )


async def test_rest_dependencies_are_declared_and_resolved() -> None:
    service, _, _ = build_service()
    principal = make_principal()
    await create_named(service, principal, "base-skill")
    await service.publish(principal, "base-skill", semver="1.0.0", changelog="base v1")
    await create_demo(service, principal)

    async def override_service() -> AsyncIterator[SkillService]:
        yield service

    app.dependency_overrides[get_skill_service] = override_service
    app.dependency_overrides[current_principal] = lambda: principal
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            published = await client.post(
                "/api/v1/skills/demo-skill/publish",
                headers={"If-Match": '"0"'},
                json={
                    "semver": "1.0.0",
                    "changelog": "uses base",
                    "dependencies": [
                        {"slug": "base-skill", "constraint": "^1.0.0"},
                    ],
                },
            )
            assert published.status_code == 200

            detail = await client.get("/api/v1/skills/demo-skill/versions/1.0.0")
            assert detail.status_code == 200
            assert detail.json()["dependencies"] == [
                {
                    "slug": "base-skill",
                    "constraint": "^1.0.0",
                    "resolved_semver": "1.0.0",
                }
            ]

            cycle = await client.post(
                "/api/v1/skills/demo-skill/publish",
                headers={"If-Match": '"1"'},
                json={
                    "semver": "1.1.0",
                    "changelog": "self dependency",
                    "dependencies": [
                        {"slug": "demo-skill", "constraint": "^1.0.0"},
                    ],
                },
            )
            assert cycle.status_code == 422
            assert "elle-même" in cycle.json()["error"]["message"]
    finally:
        app.dependency_overrides.clear()


async def test_rest_skills_flow() -> None:
    service, _, _ = build_service()
    principal = make_principal()

    async def override_service() -> AsyncIterator[SkillService]:
        yield service

    app.dependency_overrides[get_skill_service] = override_service
    app.dependency_overrides[current_principal] = lambda: principal
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/v1/skills",
                json={
                    "slug": "demo-skill",
                    "domain": "security",
                    "files": [
                        {
                            "path": "SKILL.md",
                            "content_b64": base64.b64encode(SKILL_MD).decode("ascii"),
                            "mode": "755",
                        }
                    ],
                },
            )
            assert created.status_code == 201
            assert created.headers["etag"] == '"0"'
            assert created.json()["skill"]["slug"] == "demo-skill"

            draft = await client.get("/api/v1/skills/demo-skill/draft")
            assert draft.status_code == 200
            assert draft.headers["etag"] == '"0"'
            assert draft.json()["files"][0]["content_b64"] == base64.b64encode(SKILL_MD).decode(
                "ascii"
            )
            assert draft.json()["files"][0]["mode"] == "0755"

            updated = await client.put(
                "/api/v1/skills/demo-skill/draft/files/notes.txt",
                headers={"If-Match": '"0"'},
                json={"content_b64": base64.b64encode(b"notes").decode("ascii")},
            )
            assert updated.status_code == 200
            assert updated.headers["etag"] == '"1"'

            stale_put = await client.put(
                "/api/v1/skills/demo-skill/draft/files/notes.txt",
                headers={"If-Match": '"0"'},
                json={"content_b64": base64.b64encode(b"stale").decode("ascii")},
            )
            assert stale_put.status_code == 412

            invalid_etag = await client.put(
                "/api/v1/skills/demo-skill/draft/files/notes.txt",
                headers={"If-Match": "not-an-etag"},
                json={"content_b64": base64.b64encode(b"bad").decode("ascii")},
            )
            assert invalid_etag.status_code == 412

            missing_precondition = await client.post(
                "/api/v1/skills/demo-skill/publish",
                json={"semver": "1.0.0", "changelog": "Initial version"},
            )
            assert missing_precondition.status_code == 412

            published = await client.post(
                "/api/v1/skills/demo-skill/publish",
                headers={"If-Match": '"1"'},
                json={"semver": "1.0.0", "changelog": "Initial version"},
            )
            assert published.status_code == 200
            assert published.json()["semver"] == "1.0.0"
            assert published.json()["origin_kind"] == "app"

            stale = await client.post(
                "/api/v1/skills/demo-skill/publish",
                headers={"If-Match": '"1"'},
                json={"semver": "1.0.1", "changelog": "stale"},
            )
            assert stale.status_code == 412

            versions = await client.get("/api/v1/skills/demo-skill/versions")
            assert versions.status_code == 200
            assert len(versions.json()) == 1

            added = await client.put(
                "/api/v1/skills/demo-skill/draft/files/extra.txt",
                headers={"If-Match": '"2"'},
                json={"content_b64": base64.b64encode(b"extra\n").decode("ascii")},
            )
            assert added.status_code == 200
            assert added.headers["etag"] == '"3"'

            second = await client.post(
                "/api/v1/skills/demo-skill/publish",
                headers={"If-Match": '"3"'},
                json={"semver": "1.1.0", "changelog": "Second version"},
            )
            assert second.status_code == 200
            assert second.json()["semver"] == "1.1.0"

            diff = await client.get(
                "/api/v1/skills/demo-skill/diff",
                params={"from": "1.0.0", "to": "1.1.0"},
            )
            assert diff.status_code == 200
            assert diff.json()["slug"] == "demo-skill"
            assert [(item["path"], item["change"]) for item in diff.json()["files"]] == [
                ("extra.txt", "added")
            ]
            assert "+extra" in diff.json()["files"][0]["diff"]

            unknown_version = await client.get(
                "/api/v1/skills/demo-skill/diff",
                params={"from": "1.0.0", "to": "9.9.9"},
            )
            assert unknown_version.status_code == 404

            history = await client.get("/api/v1/skills/demo-skill/history")
            assert history.status_code == 200
            assert history.json()["slug"] == "demo-skill"
            assert history.json()["head"] == "1.1.0"
            assert [entry["semver"] for entry in history.json()["versions"]] == [
                "1.1.0",
                "1.0.0",
            ]
            latest, first = history.json()["versions"]
            assert latest["parent_semver"] == "1.0.0"
            assert latest["changelog"] == "Second version"
            assert latest["changes"]["files_added"] == 1
            assert latest["changes"]["insertions"] == 1
            assert first["parent_semver"] is None

            previous = await client.get("/api/v1/skills/demo-skill/versions/1.0.0")
            assert previous.status_code == 200
            assert previous.json()["version"]["status"] == "published"
    finally:
        app.dependency_overrides.clear()
