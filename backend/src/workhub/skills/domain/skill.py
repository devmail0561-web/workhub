"""Domaine des Skills : fichiers, manifeste canonique et versions."""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from typing import cast
from uuid import UUID

from workhub.shared.api import ValidationError

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
MODE_PATTERN = re.compile(r"^[0-7]{4}$")
REQUIREMENT_KINDS = frozenset({"package", "system", "service", "script"})
REQUIREMENT_USAGES = frozenset({"required", "optional"})
MANIFEST_VERSION = 1

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_VERSION_BYTES = 50 * 1024 * 1024
MAX_FILES = 500
MAX_CHANGELOG_LENGTH = 10_000
MAX_DIFF_CHARS = 200_000

SemVerKey = tuple[int, int, int, int, tuple[tuple[int, int, str], ...]]
_REQUIREMENT_FIELDS = frozenset(
    {
        "kind",
        "ecosystem",
        "name",
        "version_constraint",
        "pinned_version",
        "hashes",
        "check_command",
        "tool_version_id",
        "usage",
        "note",
    }
)
_REQUIREMENT_TEXT_FIELDS = (
    "ecosystem",
    "name",
    "version_constraint",
    "pinned_version",
    "check_command",
    "note",
)


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
    origin_kind: str = "app"
    origin_integration_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class StoredFile:
    """Référence d'un fichier déjà adressé par contenu."""

    path: str
    sha256: bytes
    size: int
    mode: str


@dataclass(frozen=True, slots=True)
class FileDiff:
    """Différence entre deux versions d'un même chemin."""

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
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class DiffStats:
    """Statistiques agrégées d'un ensemble de différences."""

    files_added: int
    files_modified: int
    files_deleted: int
    insertions: int
    deletions: int


@dataclass(frozen=True, slots=True)
class SkillMetadata:
    """Métadonnées minimales lues dans le frontmatter de SKILL.md."""

    name: str
    description: str


def validate_slug(slug: str) -> str:
    """Valide et retourne un slug de Skill."""
    normalized = slug.strip()
    if not 1 <= len(normalized) <= 200 or not SLUG_PATTERN.fullmatch(normalized):
        raise ValidationError(
            "Le slug doit être en minuscules, sans espace, avec des tirets simples"
        )
    return normalized


def validate_semver(semver: str) -> str:
    """Valide et retourne une version SemVer stricte."""
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
    """Valide un chemin relatif portable, sans segment ambigu."""
    parts = path.split("/")
    if (
        not path
        or len(path) > 1024
        or path.startswith("/")
        or "\\" in path
        or path.endswith("/")
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValidationError(f"Chemin de fichier invalide : {path!r}")
    return path


def validate_mode(mode: str) -> str:
    """Valide et normalise un mode de fichier Unix sur quatre chiffres."""
    normalized = mode.strip()
    if len(normalized) == 3:
        normalized = f"0{normalized}"
    if not MODE_PATTERN.fullmatch(normalized):
        raise ValidationError(f"Mode de fichier invalide : {mode!r}")
    return normalized


def validate_files(files: tuple[SkillFile, ...], *, slug: str) -> tuple[SkillFile, ...]:
    """Valide l'ensemble des fichiers d'une version de Skill."""
    if not files:
        raise ValidationError("Une Skill doit contenir au moins SKILL.md")
    if len(files) > MAX_FILES:
        raise ValidationError(f"Une Skill ne peut pas contenir plus de {MAX_FILES} fichiers")

    seen: set[str] = set()
    total = 0
    normalized_files: list[SkillFile] = []
    for file in files:
        normalized_path = validate_path(file.path)
        normalized_mode = validate_mode(file.mode)
        if normalized_path in seen:
            raise ValidationError(f"Chemin dupliqué : {normalized_path}")
        seen.add(normalized_path)
        if file.size > MAX_FILE_BYTES:
            raise ValidationError(
                f"Le fichier {normalized_path} dépasse la limite de {MAX_FILE_BYTES} octets"
            )
        total += file.size
        normalized_files.append(replace(file, path=normalized_path, mode=normalized_mode))
    if total > MAX_VERSION_BYTES:
        raise ValidationError(
            f"Une version de Skill ne peut pas dépasser {MAX_VERSION_BYTES} octets"
        )
    if "SKILL.md" not in seen:
        raise ValidationError("SKILL.md est obligatoire")

    normalized_tuple = tuple(sorted(normalized_files, key=lambda item: item.path))
    skill_metadata(normalized_tuple, slug=slug)
    return normalized_tuple


def skill_metadata(files: Iterable[SkillFile], *, slug: str) -> SkillMetadata:
    """Extrait et valide le frontmatter de SKILL.md."""
    skill_md = next((file for file in files if file.path == "SKILL.md"), None)
    if skill_md is None:
        raise ValidationError("SKILL.md est obligatoire")
    return parse_skill_md(skill_md.content, slug=slug)


def parse_skill_md(content: bytes, *, slug: str) -> SkillMetadata:
    """Valide le frontmatter YAML minimal et retourne ses métadonnées."""
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
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip("\"'")
    name = fields.get("name", "")
    description = fields.get("description", "")
    if name != slug:
        raise ValidationError("Le champ name de SKILL.md doit être égal au slug")
    if not description:
        raise ValidationError("Le champ description de SKILL.md est obligatoire")
    return SkillMetadata(name=name, description=description)


def normalize_requirements(
    requirements: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Valide, normalise et trie les exigences du manifeste."""
    normalized: list[dict[str, object]] = []
    for raw in requirements:
        unknown = set(raw) - _REQUIREMENT_FIELDS
        if unknown:
            raise ValidationError(
                "Champ d'exigence inconnu : " + ", ".join(sorted(str(item) for item in unknown))
            )
        kind = _required_text(raw.get("kind"), "kind")
        if kind not in REQUIREMENT_KINDS:
            raise ValidationError(f"Type d'exigence invalide : {kind!r}")
        usage = _optional_text(raw.get("usage")) or "required"
        if usage not in REQUIREMENT_USAGES:
            raise ValidationError(f"Usage d'exigence invalide : {usage!r}")

        item: dict[str, object] = {"kind": kind, "usage": usage}
        for field in _REQUIREMENT_TEXT_FIELDS:
            value = _optional_text(raw.get(field))
            if value is not None:
                item[field] = value

        hashes = _normalize_hashes(raw.get("hashes"))
        if hashes:
            item["hashes"] = hashes
        tool_version_id = _normalize_uuid(raw.get("tool_version_id"), "tool_version_id")
        if tool_version_id is not None:
            item["tool_version_id"] = tool_version_id

        if kind == "package":
            if "ecosystem" not in item or "name" not in item:
                raise ValidationError("Une exigence package requiert ecosystem et name")
            if tool_version_id is not None:
                raise ValidationError("Une exigence package ne peut pas cibler tool_version_id")
        elif kind == "script":
            if tool_version_id is None:
                raise ValidationError("Une exigence script requiert tool_version_id")
            if "name" in item:
                raise ValidationError("Une exigence script ne peut pas définir name")
        else:
            if "name" not in item:
                raise ValidationError(f"Une exigence {kind} requiert name")
            if tool_version_id is not None:
                raise ValidationError(f"Une exigence {kind} ne peut pas cibler tool_version_id")

        normalized.append(item)

    unique: dict[str, dict[str, object]] = {}
    for item in normalized:
        unique[_canonical_json(item)] = item
    return tuple(unique[key] for key in sorted(unique))


def build_manifest(
    *,
    slug: str,
    name: str,
    description: str,
    semver: str,
    parent: str | None,
    files: tuple[SkillFile, ...],
    requirements: tuple[Mapping[str, object], ...] = (),
    dependencies: tuple[Mapping[str, object], ...] = (),
) -> dict[str, object]:
    """Construit le manifeste canonique d'une version."""
    entries = [
        {
            "path": file.path,
            "sha256": file.sha256.hex(),
            "size": file.size,
            "mode": validate_mode(file.mode),
        }
        for file in sorted(files, key=lambda item: item.path)
    ]
    normalized_requirements = normalize_requirements(requirements)
    normalized_dependencies = sorted(
        (dict(dependency) for dependency in dependencies),
        key=_canonical_json,
    )
    return {
        "manifest_version": MANIFEST_VERSION,
        "name": name,
        "slug": slug,
        "description": description,
        "semver": semver,
        "parent": parent,
        "files": entries,
        "dependencies": normalized_dependencies,
        "requirements": list(normalized_requirements),
    }


def manifest_sha256(manifest: dict[str, object]) -> bytes:
    """Calcule l'empreinte du manifeste canonique (JSON trié, UTF-8)."""
    payload = _canonical_json(manifest).encode("utf-8")
    return sha256(payload).digest()


def diff_files(
    before: tuple[SkillFile, ...],
    after: tuple[SkillFile, ...],
) -> tuple[FileDiff, ...]:
    """Compare deux ensembles de fichiers et produit des diffs unifiés."""
    before_by_path = {file.path: file for file in before}
    after_by_path = {file.path: file for file in after}
    diffs: list[FileDiff] = []
    for path in sorted(before_by_path.keys() | after_by_path.keys()):
        old = before_by_path.get(path)
        new = after_by_path.get(path)
        if old is None and new is None:
            continue
        if old is None:
            change = "added"
        elif new is None:
            change = "deleted"
        elif old.sha256 == new.sha256 and old.mode == new.mode:
            continue
        else:
            change = "modified"
        text, binary, truncated = _render_text_diff(path, old, new)
        diffs.append(
            FileDiff(
                path=path,
                change=change,
                before_sha256=old.sha256 if old is not None else None,
                after_sha256=new.sha256 if new is not None else None,
                before_size=old.size if old is not None else 0,
                after_size=new.size if new is not None else 0,
                before_mode=old.mode if old is not None else None,
                after_mode=new.mode if new is not None else None,
                binary=binary,
                text=text,
                truncated=truncated,
            )
        )
    return tuple(diffs)


def summarize_diff(diffs: Iterable[FileDiff]) -> DiffStats:
    """Agrège les changements de fichiers en statistiques de type `git log`."""
    files_added = 0
    files_modified = 0
    files_deleted = 0
    insertions = 0
    deletions = 0
    for diff in diffs:
        if diff.change == "added":
            files_added += 1
        elif diff.change == "deleted":
            files_deleted += 1
        else:
            files_modified += 1
        if diff.text:
            for line in diff.text.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    insertions += 1
                elif line.startswith("-") and not line.startswith("---"):
                    deletions += 1
    return DiffStats(
        files_added=files_added,
        files_modified=files_modified,
        files_deleted=files_deleted,
        insertions=insertions,
        deletions=deletions,
    )


def _render_text_diff(
    path: str,
    old: SkillFile | None,
    new: SkillFile | None,
) -> tuple[str | None, bool, bool]:
    old_text = _decode_text(old.content) if old is not None else ""
    new_text = _decode_text(new.content) if new is not None else ""
    if old_text is None or new_text is None:
        return None, True, False
    lines = list(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=f"a/{path}" if old is not None else "/dev/null",
            tofile=f"b/{path}" if new is not None else "/dev/null",
            lineterm="",
        )
    )
    text = "\n".join(lines)
    if len(text) > MAX_DIFF_CHARS:
        return text[:MAX_DIFF_CHARS], False, True
    return text, False, False


def _decode_text(content: bytes) -> str | None:
    if b"\x00" in content:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def semver_key(value: str) -> SemVerKey:
    """Clé de comparaison SemVer conforme à la précédence des préreleases."""
    match = SEMVER_PATTERN.fullmatch(value)
    if match is None:
        raise ValidationError(f"Version SemVer invalide : {value!r}")
    major, minor, patch = (int(match.group(index)) for index in (1, 2, 3))
    prerelease = match.group(4)
    if prerelease is None:
        return (major, minor, patch, 1, ())
    identifiers = tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part) for part in prerelease.split(".")
    )
    return (major, minor, patch, 0, identifiers)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"Le champ {field} est obligatoire")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError("Une valeur textuelle d'exigence est invalide")
    normalized = value.strip()
    return normalized or None


def _normalize_hashes(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValidationError("Le champ hashes doit être un objet")
    normalized: dict[str, str] = {}
    for key, item in cast("Mapping[object, object]", value).items():
        if not isinstance(key, str) or not key.strip() or not isinstance(item, str):
            raise ValidationError("Le champ hashes doit contenir des couples texte/texte")
        if not item.strip():
            raise ValidationError("Une valeur de hash ne peut pas être vide")
        normalized[key.strip()] = item.strip()
    return normalized or None


def _normalize_uuid(value: object, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    if not isinstance(value, str):
        raise ValidationError(f"Le champ {field} doit être un UUID")
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValidationError(f"Le champ {field} doit être un UUID") from exc
