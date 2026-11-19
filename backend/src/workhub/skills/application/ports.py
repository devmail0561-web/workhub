"""Ports du module Skills."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID

from workhub.skills.domain.skill import (
    Skill,
    SkillDraft,
    SkillFile,
    SkillVersion,
    StoredFile,
)

Commit = Callable[[], Awaitable[None]]


class SkillRepository(Protocol):
    """Persistance des Skills, brouillons, blobs et versions."""

    async def find_by_slug(self, slug: str) -> Skill | None: ...

    async def list_for_owner(self, owner_id: UUID) -> list[Skill]: ...

    async def add_skill(self, skill: Skill) -> None: ...

    async def update_skill_status(self, skill_id: UUID, status: str) -> None: ...

    async def add_draft(self, draft: SkillDraft) -> None: ...

    async def find_draft(self, skill_id: UUID) -> SkillDraft | None: ...

    async def touch_draft(self, draft_id: UUID, updated_at: datetime) -> None: ...

    async def update_draft_base(
        self,
        draft_id: UUID,
        version_id: UUID,
        updated_at: datetime,
    ) -> None: ...

    async def store_blob(self, content: bytes) -> bytes: ...

    async def read_blob(self, sha256: bytes) -> bytes | None: ...

    async def put_draft_file(
        self,
        draft_id: UUID,
        path: str,
        blob_sha256: bytes,
        mode: str,
    ) -> None: ...

    async def delete_draft_file(self, draft_id: UUID, path: str) -> None: ...

    async def list_draft_files(self, draft_id: UUID) -> list[StoredFile]: ...

    async def add_version(
        self,
        version: SkillVersion,
        files: tuple[SkillFile, ...],
        requirements: tuple[dict[str, object], ...],
    ) -> None: ...

    async def list_versions(self, skill_id: UUID) -> list[SkillVersion]: ...

    async def find_version(self, skill_id: UUID, semver: str) -> SkillVersion | None: ...

    async def list_version_files(self, version_id: UUID) -> list[StoredFile]: ...
