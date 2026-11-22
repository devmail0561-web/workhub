"""Routes REST du module Skills."""

from __future__ import annotations

import base64
import binascii
import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from pydantic import BaseModel, Field

from workhub.interfaces.rest.dependencies import current_principal
from workhub.interfaces.rest.middleware import get_request_id
from workhub.shared.api import PreconditionFailedError, Principal, ValidationError
from workhub.skills.api import (
    CreatedSkillView,
    DiffStats,
    DraftFileView,
    DraftView,
    FileDiffView,
    SkillFile,
    SkillService,
    SkillView,
    StoredFile,
    VersionDetailView,
    VersionDiffView,
    VersionHistoryView,
    VersionLogEntryView,
    VersionView,
    get_skill_service,
)

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])
_ETAG_PATTERN = re.compile(r'^"([0-9]+)"$')


def _parse_if_match(if_match: str | None) -> int | None:
    if if_match is None:
        raise PreconditionFailedError("En-tête If-Match requis")
    normalized = if_match.strip()
    if normalized == "*":
        return None
    match = _ETAG_PATTERN.fullmatch(normalized)
    if match is None:
        raise PreconditionFailedError("ETag invalide dans If-Match")
    return int(match.group(1))


def _set_etag(response: Response, lock_version: int) -> None:
    response.headers["ETag"] = f'"{lock_version}"'


class SkillFileRequest(BaseModel):
    """Fichier transmis en base64 pour préserver les octets."""

    path: str = Field(min_length=1, max_length=1024)
    content_b64: str = Field(min_length=1)
    mode: str = Field(default="0644", pattern=r"^[0-7]{3,4}$")


class CreateSkillRequest(BaseModel):
    """Création d'une Skill et de son brouillon initial."""

    slug: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=1, max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=50)
    files: list[SkillFileRequest] = Field(min_length=1, max_length=500)


class PutFileRequest(BaseModel):
    """Remplacement d'un fichier du brouillon."""

    content_b64: str = Field(min_length=1)
    mode: str = Field(default="0644", pattern=r"^[0-7]{3,4}$")


class RequirementRequest(BaseModel):
    """Exigence déclarée dans le manifeste d'une Skill."""

    kind: str = Field(min_length=1, max_length=20)
    ecosystem: str | None = Field(default=None, max_length=50)
    name: str | None = Field(default=None, max_length=200)
    version_constraint: str | None = Field(default=None, max_length=200)
    pinned_version: str | None = Field(default=None, max_length=100)
    hashes: dict[str, str] | None = None
    check_command: str | None = Field(default=None, max_length=500)
    tool_version_id: UUID | None = None
    usage: str = Field(default="required", pattern=r"^(required|optional)$")
    note: str | None = Field(default=None, max_length=1000)

    def to_payload(self) -> dict[str, object]:
        """Convertit l'entrée en dictionnaire compatible manifeste."""
        return {
            key: value
            for key, value in self.model_dump(mode="json", exclude_none=True).items()
            if value is not None
        }


class PublishRequest(BaseModel):
    """Publication d'une version immuable."""

    semver: str = Field(min_length=1, max_length=100)
    changelog: str = Field(min_length=1, max_length=10_000)
    requirements: list[RequirementRequest] | None = Field(default=None, max_length=100)


class SkillResponse(BaseModel):
    """Skill exposée."""

    id: UUID
    slug: str
    domain: str
    status: str
    tags: list[str]
    created_at: datetime

    @classmethod
    def from_view(cls, skill: SkillView) -> SkillResponse:
        return cls(
            id=skill.id,
            slug=skill.slug,
            domain=skill.domain,
            status=skill.status,
            tags=list(skill.tags),
            created_at=skill.created_at,
        )


class DraftFileResponse(BaseModel):
    """Fichier de brouillon avec son contenu encodé."""

    path: str
    content_b64: str
    mode: str
    sha256: str
    size: int

    @classmethod
    def from_view(cls, file: DraftFileView) -> DraftFileResponse:
        return cls(
            path=file.path,
            content_b64=base64.b64encode(file.content).decode("ascii"),
            mode=file.mode,
            sha256=file.sha256.hex(),
            size=file.size,
        )


class DraftResponse(BaseModel):
    """Brouillon complet d'une Skill."""

    skill: SkillResponse
    lock_version: int
    updated_at: datetime
    files: list[DraftFileResponse]

    @classmethod
    def from_view(cls, draft: DraftView) -> DraftResponse:
        return cls(
            skill=SkillResponse.from_view(draft.skill),
            lock_version=draft.lock_version,
            updated_at=draft.updated_at,
            files=[DraftFileResponse.from_view(file) for file in draft.files],
        )


class CreatedSkillResponse(BaseModel):
    """Skill et brouillon créés ensemble."""

    skill: SkillResponse
    draft: DraftResponse

    @classmethod
    def from_view(cls, created: CreatedSkillView) -> CreatedSkillResponse:
        return cls(
            skill=SkillResponse.from_view(created.skill),
            draft=DraftResponse.from_view(created.draft),
        )


class VersionResponse(BaseModel):
    """Version publiée exposée."""

    id: UUID
    semver: str
    status: str
    changelog: str
    manifest_sha256: str
    parent_semver: str | None
    origin_kind: str
    origin_integration_id: UUID | None
    created_at: datetime
    published_at: datetime

    @classmethod
    def from_view(cls, version: VersionView) -> VersionResponse:
        return cls(
            id=version.id,
            semver=version.semver,
            status=version.status,
            changelog=version.changelog,
            manifest_sha256=version.manifest_sha256.hex(),
            parent_semver=version.parent_semver,
            origin_kind=version.origin_kind,
            origin_integration_id=version.origin_integration_id,
            created_at=version.created_at,
            published_at=version.published_at,
        )


class StoredFileResponse(BaseModel):
    """Métadonnées d'un fichier publié."""

    path: str
    sha256: str
    size: int
    mode: str

    @classmethod
    def from_stored(cls, file: StoredFile) -> StoredFileResponse:
        return cls(path=file.path, sha256=file.sha256.hex(), size=file.size, mode=file.mode)


class VersionDetailResponse(BaseModel):
    """Version publiée avec fichiers et manifeste."""

    version: VersionResponse
    files: list[StoredFileResponse]
    manifest: dict[str, object]

    @classmethod
    def from_view(cls, detail: VersionDetailView) -> VersionDetailResponse:
        return cls(
            version=VersionResponse.from_view(detail.version),
            files=[StoredFileResponse.from_stored(file) for file in detail.files],
            manifest=detail.manifest,
        )


class FileDiffResponse(BaseModel):
    """Différence d'un fichier entre deux versions."""

    path: str
    change: str
    before_sha256: str | None
    after_sha256: str | None
    before_size: int
    after_size: int
    before_mode: str | None
    after_mode: str | None
    binary: bool
    diff: str | None
    truncated: bool

    @classmethod
    def from_view(cls, diff: FileDiffView) -> FileDiffResponse:
        return cls(
            path=diff.path,
            change=diff.change,
            before_sha256=diff.before_sha256.hex() if diff.before_sha256 is not None else None,
            after_sha256=diff.after_sha256.hex() if diff.after_sha256 is not None else None,
            before_size=diff.before_size,
            after_size=diff.after_size,
            before_mode=diff.before_mode,
            after_mode=diff.after_mode,
            binary=diff.binary,
            diff=diff.text,
            truncated=diff.truncated,
        )


class VersionDiffResponse(BaseModel):
    """Comparaison de deux versions publiées."""

    slug: str
    from_semver: str
    to_semver: str
    files: list[FileDiffResponse]

    @classmethod
    def from_view(cls, diff: VersionDiffView) -> VersionDiffResponse:
        return cls(
            slug=diff.slug,
            from_semver=diff.from_semver,
            to_semver=diff.to_semver,
            files=[FileDiffResponse.from_view(file) for file in diff.files],
        )


class DiffStatsResponse(BaseModel):
    """Statistiques agrégées d'un changement de version."""

    files_added: int
    files_modified: int
    files_deleted: int
    insertions: int
    deletions: int

    @classmethod
    def from_stats(cls, stats: DiffStats) -> DiffStatsResponse:
        return cls(
            files_added=stats.files_added,
            files_modified=stats.files_modified,
            files_deleted=stats.files_deleted,
            insertions=stats.insertions,
            deletions=stats.deletions,
        )


class VersionLogEntryResponse(BaseModel):
    """Entrée d'historique d'une version, à la manière d'un commit Git."""

    id: UUID
    semver: str
    parent_semver: str | None
    status: str
    changelog: str
    author_principal_id: UUID
    manifest_sha256: str
    origin_kind: str
    origin_integration_id: UUID | None
    created_at: datetime
    published_at: datetime
    changes: DiffStatsResponse

    @classmethod
    def from_view(cls, entry: VersionLogEntryView) -> VersionLogEntryResponse:
        return cls(
            id=entry.id,
            semver=entry.semver,
            parent_semver=entry.parent_semver,
            status=entry.status,
            changelog=entry.changelog,
            author_principal_id=entry.author_principal_id,
            manifest_sha256=entry.manifest_sha256.hex(),
            origin_kind=entry.origin_kind,
            origin_integration_id=entry.origin_integration_id,
            created_at=entry.created_at,
            published_at=entry.published_at,
            changes=DiffStatsResponse.from_stats(entry.changes),
        )


class VersionHistoryResponse(BaseModel):
    """Historique complet d'une Skill, du plus récent au plus ancien."""

    slug: str
    head: str | None
    versions: list[VersionLogEntryResponse]

    @classmethod
    def from_view(cls, history: VersionHistoryView) -> VersionHistoryResponse:
        return cls(
            slug=history.slug,
            head=history.head,
            versions=[VersionLogEntryResponse.from_view(entry) for entry in history.versions],
        )


def _decode_file(file: SkillFileRequest) -> SkillFile:
    try:
        content = base64.b64decode(file.content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError(f"Contenu base64 invalide pour {file.path}") from exc
    return SkillFile(path=file.path, content=content, mode=file.mode)


def _decode_content(content_b64: str) -> bytes:
    try:
        return base64.b64decode(content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError("Contenu base64 invalide") from exc


@router.post("", response_model=CreatedSkillResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(
    payload: CreateSkillRequest,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> CreatedSkillResponse:
    """Crée une Skill brouillon."""
    created = await service.create(
        principal,
        slug=payload.slug,
        domain=payload.domain,
        tags=tuple(payload.tags),
        files=tuple(_decode_file(file) for file in payload.files),
        request_id=get_request_id(request),
    )
    _set_etag(response, created.draft.lock_version)
    return CreatedSkillResponse.from_view(created)


@router.get("", response_model=list[SkillResponse])
async def list_skills(
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> list[SkillResponse]:
    """Liste les Skills du principal."""
    return [SkillResponse.from_view(skill) for skill in await service.list(principal)]


@router.get("/{slug}", response_model=SkillResponse)
async def get_skill(
    slug: str,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> SkillResponse:
    """Retourne une Skill."""
    return SkillResponse.from_view(await service.get(principal, slug))


@router.get("/{slug}/draft", response_model=DraftResponse)
async def get_draft(
    slug: str,
    response: Response,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> DraftResponse:
    """Retourne le brouillon courant."""
    draft = await service.get_draft(principal, slug)
    _set_etag(response, draft.lock_version)
    return DraftResponse.from_view(draft)


@router.put("/{slug}/draft/files/{path:path}", response_model=DraftResponse)
async def put_draft_file(
    slug: str,
    path: str,
    payload: PutFileRequest,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> DraftResponse:
    """Crée ou remplace un fichier du brouillon."""
    draft = await service.put_file(
        principal,
        slug,
        path=path,
        content=_decode_content(payload.content_b64),
        mode=payload.mode,
        expected_lock_version=_parse_if_match(if_match),
        request_id=get_request_id(request),
    )
    _set_etag(response, draft.lock_version)
    return DraftResponse.from_view(draft)


@router.delete("/{slug}/draft/files/{path:path}", response_model=DraftResponse)
async def delete_draft_file(
    slug: str,
    path: str,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> DraftResponse:
    """Supprime un fichier du brouillon."""
    draft = await service.delete_file(
        principal,
        slug,
        path=path,
        expected_lock_version=_parse_if_match(if_match),
        request_id=get_request_id(request),
    )
    _set_etag(response, draft.lock_version)
    return DraftResponse.from_view(draft)


@router.post("/{slug}/publish", response_model=VersionResponse)
async def publish_skill(
    slug: str,
    payload: PublishRequest,
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> VersionResponse:
    """Publie une nouvelle version immuable."""
    version = await service.publish(
        principal,
        slug,
        semver=payload.semver,
        changelog=payload.changelog,
        requirements=tuple(
            requirement.to_payload() for requirement in (payload.requirements or ())
        ),
        expected_lock_version=_parse_if_match(if_match),
        request_id=get_request_id(request),
    )
    return VersionResponse.from_view(version)


@router.get("/{slug}/versions", response_model=list[VersionResponse])
async def list_versions(
    slug: str,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> list[VersionResponse]:
    """Liste les versions d'une Skill."""
    return [
        VersionResponse.from_view(version)
        for version in await service.list_versions(principal, slug)
    ]


@router.get("/{slug}/versions/{semver}", response_model=VersionDetailResponse)
async def get_version(
    slug: str,
    semver: str,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> VersionDetailResponse:
    """Retourne une version publiée."""
    return VersionDetailResponse.from_view(await service.get_version(principal, slug, semver))


@router.get("/{slug}/diff", response_model=VersionDiffResponse)
async def diff_versions(
    slug: str,
    from_semver: Annotated[str, Query(alias="from")],
    to_semver: Annotated[str, Query(alias="to")],
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> VersionDiffResponse:
    """Compare deux versions publiées."""
    return VersionDiffResponse.from_view(
        await service.diff(
            principal,
            slug,
            from_semver=from_semver,
            to_semver=to_semver,
        )
    )


@router.get("/{slug}/history", response_model=VersionHistoryResponse)
async def get_version_history(
    slug: str,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> VersionHistoryResponse:
    """Retrace l'historique des versions, du plus récent au plus ancien."""
    return VersionHistoryResponse.from_view(await service.history(principal, slug))
