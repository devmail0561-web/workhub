"""Faux dépôt Skills pour les tests unitaires."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from workhub.skills.domain.skill import (
    Skill,
    SkillDraft,
    SkillFile,
    SkillVersion,
    StoredFile,
)


class FakeSkillRepository:
    """Dépôt en mémoire, suffisant pour les cas d'usage Skills."""

    def __init__(self) -> None:
        self.skills: dict[UUID, Skill] = {}
        self.drafts: dict[UUID, SkillDraft] = {}
        self.draft_files: dict[tuple[UUID, str], StoredFile] = {}
        self.blobs: dict[bytes, bytes] = {}
        self.versions: dict[UUID, SkillVersion] = {}
        self.version_files: dict[UUID, list[StoredFile]] = {}
        self.requirements: dict[UUID, tuple[dict[str, object], ...]] = {}

    async def find_by_slug(self, slug: str) -> Skill | None:
        return next((skill for skill in self.skills.values() if skill.slug == slug), None)

    async def list_visible(self, owner_id: UUID, *, include_all: bool) -> list[Skill]:
        if include_all:
            return list(self.skills.values())
        return [
            skill
            for skill in self.skills.values()
            if skill.owner_id == owner_id or skill.status in {"published", "deprecated"}
        ]

    async def add_skill(self, skill: Skill) -> None:
        self.skills[skill.id] = skill

    async def update_skill_status(self, skill_id: UUID, status: str) -> None:
        self.skills[skill_id] = replace(self.skills[skill_id], status=status)

    async def add_draft(self, draft: SkillDraft) -> None:
        self.drafts[draft.skill_id] = draft

    async def find_draft(self, skill_id: UUID) -> SkillDraft | None:
        return self.drafts.get(skill_id)

    async def touch_draft(
        self,
        draft_id: UUID,
        expected_lock_version: int,
        updated_at: datetime,
    ) -> bool:
        for skill_id, draft in list(self.drafts.items()):
            if draft.id == draft_id:
                if draft.lock_version != expected_lock_version:
                    return False
                self.drafts[skill_id] = replace(
                    draft,
                    updated_at=updated_at,
                    lock_version=draft.lock_version + 1,
                )
                return True
        return False

    async def update_draft_base(
        self,
        draft_id: UUID,
        version_id: UUID,
        expected_lock_version: int,
        updated_at: datetime,
    ) -> bool:
        for skill_id, draft in list(self.drafts.items()):
            if draft.id == draft_id:
                if draft.lock_version != expected_lock_version:
                    return False
                self.drafts[skill_id] = replace(
                    draft,
                    base_version_id=version_id,
                    updated_at=updated_at,
                    lock_version=draft.lock_version + 1,
                )
                return True
        return False

    async def store_blob(self, content: bytes) -> bytes:
        digest = sha256(content).digest()
        self.blobs[digest] = content
        return digest

    async def read_blob(self, sha256: bytes) -> bytes | None:
        return self.blobs.get(sha256)

    async def put_draft_file(
        self,
        draft_id: UUID,
        path: str,
        blob_sha256: bytes,
        mode: str,
    ) -> None:
        self.draft_files[(draft_id, path)] = StoredFile(
            path=path,
            sha256=blob_sha256,
            size=len(self.blobs[blob_sha256]),
            mode=mode,
        )

    async def delete_draft_file(self, draft_id: UUID, path: str) -> None:
        self.draft_files.pop((draft_id, path), None)

    async def list_draft_files(self, draft_id: UUID) -> list[StoredFile]:
        return [
            stored
            for (candidate_draft_id, _), stored in self.draft_files.items()
            if candidate_draft_id == draft_id
        ]

    async def add_version(
        self,
        version: SkillVersion,
        files: tuple[SkillFile, ...],
        requirements: tuple[dict[str, object], ...],
    ) -> None:
        self.versions[version.id] = version
        self.version_files[version.id] = [
            StoredFile(
                path=file.path,
                sha256=file.sha256,
                size=file.size,
                mode=file.mode,
            )
            for file in files
        ]
        self.requirements[version.id] = requirements

    async def list_versions(self, skill_id: UUID) -> list[SkillVersion]:
        return [version for version in self.versions.values() if version.skill_id == skill_id]

    async def find_version(self, skill_id: UUID, semver: str) -> SkillVersion | None:
        return next(
            (
                version
                for version in self.versions.values()
                if version.skill_id == skill_id and version.semver == semver
            ),
            None,
        )

    async def list_version_files(self, version_id: UUID) -> list[StoredFile]:
        return self.version_files.get(version_id, [])
