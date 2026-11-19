"""Vues applicatives du module Skills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from workhub.skills.domain.skill import Skill, SkillVersion, StoredFile


@dataclass(frozen=True, slots=True)
class SkillView:
    """Identité logique d'une Skill exposée par l'API."""

    id: UUID
    slug: str
    domain: str
    status: str
    tags: tuple[str, ...]
    created_at: datetime

    @classmethod
    def from_skill(cls, skill: Skill) -> SkillView:
        return cls(
            id=skill.id,
            slug=skill.slug,
            domain=skill.domain,
            status=skill.status,
            tags=skill.tags,
            created_at=skill.created_at,
        )


@dataclass(frozen=True, slots=True)
class DraftFileView:
    """Fichier de brouillon, contenu inclus pour l'éditeur."""

    path: str
    content: bytes
    mode: str
    sha256: bytes
    size: int


@dataclass(frozen=True, slots=True)
class DraftView:
    """Brouillon complet d'une Skill."""

    skill: SkillView
    lock_version: int
    updated_at: datetime
    files: tuple[DraftFileView, ...]


@dataclass(frozen=True, slots=True)
class VersionView:
    """Version publiée, sans contenu de fichier."""

    id: UUID
    semver: str
    status: str
    changelog: str
    manifest_sha256: bytes
    parent_semver: str | None
    created_at: datetime
    published_at: datetime

    @classmethod
    def from_version(
        cls,
        version: SkillVersion,
        *,
        parent_semver: str | None = None,
    ) -> VersionView:
        return cls(
            id=version.id,
            semver=version.semver,
            status=version.status,
            changelog=version.changelog,
            manifest_sha256=version.manifest_sha256,
            parent_semver=parent_semver,
            created_at=version.created_at,
            published_at=version.published_at,
        )


@dataclass(frozen=True, slots=True)
class VersionDetailView:
    """Version publiée avec métadonnées de fichiers et manifeste."""

    version: VersionView
    files: tuple[StoredFile, ...]
    manifest: dict[str, object]


@dataclass(frozen=True, slots=True)
class CreatedSkillView:
    """Skill et brouillon créés ensemble."""

    skill: SkillView
    draft: DraftView
