"""Vues applicatives du module Skills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from workhub.skills.domain.skill import DiffStats, FileDiff, Skill, SkillVersion, StoredFile


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
    origin_kind: str
    origin_integration_id: UUID | None
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
            origin_kind=version.origin_kind,
            origin_integration_id=version.origin_integration_id,
            created_at=version.created_at,
            published_at=version.published_at,
        )


@dataclass(frozen=True, slots=True)
class VersionDetailView:
    """Version publiée avec métadonnées de fichiers et manifeste."""

    version: VersionView
    files: tuple[StoredFile, ...]
    manifest: dict[str, object]
    dependencies: tuple[ResolvedDependencyView, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedDependencyView:
    """Dépendance déclarée et version publiée retenue lors de la publication."""

    slug: str
    constraint: str
    resolved_semver: str


@dataclass(frozen=True, slots=True)
class CreatedSkillView:
    """Skill et brouillon créés ensemble."""

    skill: SkillView
    draft: DraftView


@dataclass(frozen=True, slots=True)
class FileDiffView:
    """Différence d'un fichier entre deux versions."""

    path: str
    change: str
    before_sha256: bytes | None
    after_sha256: bytes | None
    before_size: int
    after_size: int
    before_mode: str | None
    after_mode: str | None
    binary: bool
    text: str | None
    truncated: bool

    @classmethod
    def from_diff(cls, diff: FileDiff) -> FileDiffView:
        return cls(
            path=diff.path,
            change=diff.change,
            before_sha256=diff.before_sha256,
            after_sha256=diff.after_sha256,
            before_size=diff.before_size,
            after_size=diff.after_size,
            before_mode=diff.before_mode,
            after_mode=diff.after_mode,
            binary=diff.binary,
            text=diff.text,
            truncated=diff.truncated,
        )


@dataclass(frozen=True, slots=True)
class VersionDiffView:
    """Comparaison de deux versions publiées."""

    slug: str
    from_semver: str
    to_semver: str
    files: tuple[FileDiffView, ...]


@dataclass(frozen=True, slots=True)
class VersionLogEntryView:
    """Entrée d'historique d'une version, à la manière d'un commit Git."""

    id: UUID
    semver: str
    parent_semver: str | None
    status: str
    changelog: str
    author_principal_id: UUID
    manifest_sha256: bytes
    origin_kind: str
    origin_integration_id: UUID | None
    created_at: datetime
    published_at: datetime
    changes: DiffStats


@dataclass(frozen=True, slots=True)
class VersionHistoryView:
    """Historique complet d'une Skill, du plus récent au plus ancien."""

    slug: str
    head: str | None
    versions: tuple[VersionLogEntryView, ...]
