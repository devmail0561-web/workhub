from __future__ import annotations

import base64
from collections.abc import AsyncIterator

import httpx
import pytest
from tests.unit.iam.fakes import FakeAuditRecorder, FakeClock, FakeCommit, make_principal
from tests.unit.skills.fakes import FakeSkillRepository

from workhub.interfaces.rest.app import app
from workhub.interfaces.rest.dependencies import current_principal
from workhub.shared.api import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    Principal,
    ValidationError,
)
from workhub.skills.api import SkillService, get_skill_service
from workhub.skills.domain.skill import (
    SkillFile,
    build_manifest,
    manifest_sha256,
    semver_key,
    validate_files,
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


def test_manifest_is_deterministic_and_depends_on_content() -> None:
    first = SkillFile(path="b.txt", content=b"b")
    second = SkillFile(path="a.txt", content=b"a")
    manifest = build_manifest(slug="demo", semver="1.0.0", parent=None, files=(first, second))
    reversed_manifest = build_manifest(
        slug="demo",
        semver="1.0.0",
        parent=None,
        files=(second, first),
    )

    assert manifest["files"] == reversed_manifest["files"]
    assert manifest_sha256(manifest) == manifest_sha256(reversed_manifest)
    changed = build_manifest(
        slug="demo",
        semver="1.0.0",
        parent=None,
        files=(SkillFile(path="a.txt", content=b"changed"), second),
    )
    assert manifest_sha256(changed) != manifest_sha256(manifest)


def test_manifest_includes_requirements() -> None:
    requirement: dict[str, object] = {
        "kind": "package",
        "ecosystem": "pypi",
        "name": "python-nmap",
    }
    manifest = build_manifest(
        slug="demo",
        semver="1.0.0",
        parent=None,
        files=(SkillFile(path="SKILL.md", content=SKILL_MD),),
        requirements=(requirement,),
    )
    assert manifest["requirements"] == [requirement]


def test_file_and_frontmatter_validation_rejects_unsafe_input() -> None:
    with pytest.raises(ValidationError):
        validate_path("../secret")
    with pytest.raises(ValidationError):
        validate_path("/absolute")
    with pytest.raises(ValidationError):
        validate_semver("1.0")
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
    assert [entry.action for entry in audit.entries] == ["skill.create", "skill.publish"]

    detail = await service.get_version(principal, "demo-skill", "1.0.0")
    assert detail.files[0].path == "SKILL.md"
    assert detail.manifest["slug"] == "demo-skill"


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
        request_id="req-put",
    )
    assert {file.path for file in updated.files} == {"SKILL.md", "notes/readme.md"}
    assert await repository.read_blob(updated.files[1].sha256) == b"notes"

    removed = await service.delete_file(owner, "demo-skill", path="notes/readme.md")
    assert [file.path for file in removed.files] == ["SKILL.md"]
    with pytest.raises(ValidationError):
        await service.delete_file(owner, "demo-skill", path="SKILL.md")
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
                        }
                    ],
                },
            )
            assert created.status_code == 201
            assert created.json()["skill"]["slug"] == "demo-skill"

            draft = await client.get("/api/v1/skills/demo-skill/draft")
            assert draft.status_code == 200
            assert draft.json()["files"][0]["content_b64"] == base64.b64encode(SKILL_MD).decode(
                "ascii"
            )

            published = await client.post(
                "/api/v1/skills/demo-skill/publish",
                json={"semver": "1.0.0", "changelog": "Initial version"},
            )
            assert published.status_code == 200
            assert published.json()["semver"] == "1.0.0"

            versions = await client.get("/api/v1/skills/demo-skill/versions")
            assert versions.status_code == 200
            assert len(versions.json()) == 1
    finally:
        app.dependency_overrides.clear()
