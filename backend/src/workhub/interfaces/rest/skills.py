"""Routes REST du module Skills."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from workhub.interfaces.rest.dependencies import current_principal
from workhub.interfaces.rest.middleware import get_request_id
from workhub.shared.api import Principal, ValidationError
from workhub.skills.api import (
    CreatedSkillView,
    DraftFileView,
    DraftView,
    SkillFile,
    SkillService,
    SkillView,
    StoredFile,
    VersionDetailView,
    VersionView,
    get_skill_service,
)

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


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
    check_command: str | None = Field(default=None, max_length=500)
    usage: str = Field(default="required", pattern=r"^(required|optional)$")
    note: str | None = Field(default=None, max_length=1000)

    def to_payload(self) -> dict[str, object]:
        """Convertit l'entrée en dictionnaire compatible manifeste."""
        return {
            key: value
            for key, value in self.model_dump(exclude_none=True).items()
            if value is not None
        }


class PublishRequest(BaseModel):
    """Publication d'une version immuable."""

    semver: str = Field(min_length=1, max_length=100)
    changelog: str = Field(min_length=1, max_length=10_000)
    requirements: list[RequirementRequest] | None = None


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
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> DraftResponse:
    """Retourne le brouillon courant."""
    return DraftResponse.from_view(await service.get_draft(principal, slug))


@router.put("/{slug}/draft/files/{path:path}", response_model=DraftResponse)
async def put_draft_file(
    slug: str,
    path: str,
    payload: PutFileRequest,
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> DraftResponse:
    """Crée ou remplace un fichier du brouillon."""
    draft = await service.put_file(
        principal,
        slug,
        path=path,
        content=_decode_content(payload.content_b64),
        mode=payload.mode,
        request_id=get_request_id(request),
    )
    return DraftResponse.from_view(draft)


@router.delete("/{slug}/draft/files/{path:path}", response_model=DraftResponse)
async def delete_draft_file(
    slug: str,
    path: str,
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> DraftResponse:
    """Supprime un fichier du brouillon."""
    draft = await service.delete_file(
        principal,
        slug,
        path=path,
        request_id=get_request_id(request),
    )
    return DraftResponse.from_view(draft)


@router.post("/{slug}/publish", response_model=VersionResponse)
async def publish_skill(
    slug: str,
    payload: PublishRequest,
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
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
