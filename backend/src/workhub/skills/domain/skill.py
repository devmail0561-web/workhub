"""Domaine des Skills : fichiers, manifeste canonique et versions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from workhub.shared.api import ValidationError

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$"
)
MODE_PATTERN = re.compile(r"^[0-7]{3,4}$")

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_VERSION_BYTES = 50 * 1024 * 1024
MAX_FILES = 500
MAX_CHANGELOG_LENGTH = 10_000


@dataclass(frozen=True, slots=True)
class SkillFile:
    """Contenu d'un fichier appartenant à une Skill."""

    path: str
    content: bytes
    mode: str = "0644"

    @property
    def sha256(self) -> bytes:
        return sha256(self.content).digest()

    @property
    def size(self) -> int:
        return len(self.content)


@dataclass(frozen=True, slots=True)
class Skill:
    """Identité logique d'une Skill, indépendante de ses versions."""

    id: UUID
    slug: str
    owner_id: UUID
    domain: str
    status: str
    tags: tuple[str, ...]
    created_at: datetime
    archived_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SkillDraft:
    """Espace de travail mutable avant publication."""

    id: UUID
    skill_id: UUID
    base_version_id: UUID | None
    updated_at: datetime
    lock_version: int


@dataclass(frozen=True, slots=True)
class SkillVersion:
    """Version publiée et immuable d'une Skill."""

    id: UUID
    skill_id: UUID
    semver: str
    manifest: dict[str, object]
    manifest_sha256: bytes
    parent_version_id: UUID | None
    status: str
    changelog: str
    author_principal_id: UUID
    created_at: datetime
    published_at: datetime


@dataclass(frozen=True, slots=True)
class StoredFile:
    """Référence d'un fichier déjà adressé par contenu."""

    path: str
    sha256: bytes
    size: int
    mode: str


def validate_slug(slug: str) -> str:
    """Valide et retourne un slug de Skill."""
    normalized = slug.strip()
    if not 1 <= len(normalized) <= 200 or not SLUG_PATTERN.fullmatch(normalized):
        raise ValidationError(
            "Le slug doit être en minuscules, sans espace, avec des tirets simples"
        )
    return normalized


def validate_semver(semver: str) -> str:
    """Valide et retourne une version SemVer."""
    normalized = semver.strip()
    if not SEMVER_PATTERN.fullmatch(normalized):
        raise ValidationError(f"Version SemVer invalide : {semver!r}")
    return normalized


def validate_changelog(changelog: str) -> str:
    """Valide un changelog obligatoire mais borné."""
    normalized = changelog.strip()
    if not 1 <= len(normalized) <= MAX_CHANGELOG_LENGTH:
        raise ValidationError(
            f"Le changelog doit contenir entre 1 et {MAX_CHANGELOG_LENGTH} caractères"
        )
    return normalized


def validate_domain(domain: str) -> str:
    """Valide le domaine fonctionnel d'une Skill."""
    normalized = domain.strip()
    if not 1 <= len(normalized) <= 200:
        raise ValidationError("Le domaine doit contenir entre 1 et 200 caractères")
    return normalized


def validate_path(path: str) -> str:
    """Valide un chemin relatif portable, sans traversée."""
    if (
        not path
        or len(path) > 1024
        or path.startswith("/")
        or "\\" in path
        or ".." in path.split("/")
        or path.endswith("/")
    ):
        raise ValidationError(f"Chemin de fichier invalide : {path!r}")
    return path


def validate_mode(mode: str) -> str:
    """Valide un mode de fichier Unix minimal."""
    if not MODE_PATTERN.fullmatch(mode):
        raise ValidationError(f"Mode de fichier invalide : {mode!r}")
    return mode


def validate_files(files: tuple[SkillFile, ...], *, slug: str) -> tuple[SkillFile, ...]:
    """Valide l'ensemble des fichiers d'une version de Skill."""
    if not files:
        raise ValidationError("Une Skill doit contenir au moins SKILL.md")
    if len(files) > MAX_FILES:
        raise ValidationError(f"Une Skill ne peut pas contenir plus de {MAX_FILES} fichiers")

    seen: set[str] = set()
    total = 0
    for file in files:
        validate_path(file.path)
        validate_mode(file.mode)
        if file.path in seen:
            raise ValidationError(f"Chemin dupliqué : {file.path}")
        seen.add(file.path)
        if file.size > MAX_FILE_BYTES:
            raise ValidationError(
                f"Le fichier {file.path} dépasse la limite de {MAX_FILE_BYTES} octets"
            )
        total += file.size
    if total > MAX_VERSION_BYTES:
        raise ValidationError(
            f"Une version de Skill ne peut pas dépasser {MAX_VERSION_BYTES} octets"
        )
    if "SKILL.md" not in seen:
        raise ValidationError("SKILL.md est obligatoire")

    skill_md = next(file for file in files if file.path == "SKILL.md")
    _validate_skill_md(skill_md.content, slug)
    return tuple(sorted(files, key=lambda item: item.path))


def _validate_skill_md(content: bytes, slug: str) -> None:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("SKILL.md doit être encodé en UTF-8") from exc
    if "\x00" in text:
        raise ValidationError("SKILL.md contient un octet nul")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValidationError("SKILL.md doit commencer par un frontmatter YAML")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValidationError("Frontmatter SKILL.md non fermé") from exc
    frontmatter = lines[1:end]
    fields: dict[str, str] = {}
    for line in frontmatter:
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip("\"'")
    if fields.get("name") != slug:
        raise ValidationError("Le champ name de SKILL.md doit être égal au slug")
    if not fields.get("description"):
        raise ValidationError("Le champ description de SKILL.md est obligatoire")


def build_manifest(
    *,
    slug: str,
    semver: str,
    parent: str | None,
    files: tuple[SkillFile, ...],
    requirements: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    """Construit le manifeste canonique d'une version."""
    entries = [
        {
            "path": file.path,
            "sha256": file.sha256.hex(),
            "size": file.size,
            "mode": file.mode,
        }
        for file in sorted(files, key=lambda item: item.path)
    ]
    return {
        "slug": slug,
        "semver": semver,
        "parent": parent,
        "files": entries,
        "dependencies": [],
        "requirements": list(requirements),
    }


def manifest_sha256(manifest: dict[str, object]) -> bytes:
    """Calcule l'empreinte du manifeste canonique (JSON trié, UTF-8)."""
    import json

    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).digest()


def semver_key(value: str) -> tuple[int, int, int, int, tuple[str, ...]]:
    """Clé de comparaison SemVer suffisante pour les publications WorkHub."""
    match = SEMVER_PATTERN.fullmatch(value)
    if match is None:
        raise ValidationError(f"Version SemVer invalide : {value!r}")
    major, minor, patch = (int(match.group(index)) for index in (1, 2, 3))
    prerelease = match.group(4)
    if prerelease is None:
        return (major, minor, patch, 1, ())
    identifiers = tuple(part for part in prerelease[1:].split(".") if part)
    return (major, minor, patch, 0, identifiers)
