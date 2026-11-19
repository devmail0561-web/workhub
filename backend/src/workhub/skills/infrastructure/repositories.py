"""Persistance SQLAlchemy du module Skills."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    BigInteger,
    DateTime,
    Integer,
    LargeBinary,
    Text,
    Uuid,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from workhub.shared.api import ConflictError
from workhub.shared.infrastructure.database import Base
from workhub.skills.domain.skill import (
    Skill,
    SkillDraft,
    SkillFile,
    SkillVersion,
    StoredFile,
)


class SkillRow(Base):
    """Table `skill`."""

    __tablename__ = "skill"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    status_logical: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BlobRow(Base):
    """Table `blob`, adressée par contenu."""

    __tablename__ = "blob"

    sha256: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SkillDraftRow(Base):
    """Table `skill_draft`."""

    __tablename__ = "skill_draft"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    skill_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    base_version_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False)


class SkillDraftFileRow(Base):
    """Table `skill_draft_file`."""

    __tablename__ = "skill_draft_file"

    draft_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    path: Mapped[str] = mapped_column(Text, primary_key=True)
    blob_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)


class SkillVersionRow(Base):
    """Table `skill_version`."""

    __tablename__ = "skill_version"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    skill_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    semver: Mapped[str] = mapped_column(Text, nullable=False)
    manifest: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    manifest_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    parent_version_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    changelog: Mapped[str] = mapped_column(Text, nullable=False)
    author_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    origin_kind: Mapped[str] = mapped_column(Text, nullable=False)
    origin_integration_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SkillVersionFileRow(Base):
    """Table `skill_version_file`."""

    __tablename__ = "skill_version_file"

    version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    path: Mapped[str] = mapped_column(Text, primary_key=True)
    blob_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)


class SkillRequirementRow(Base):
    """Table `skill_requirement`."""

    __tablename__ = "skill_requirement"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    skill_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    ecosystem: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    version_constraint: Mapped[str | None] = mapped_column(Text)
    pinned_version: Mapped[str | None] = mapped_column(Text)
    hashes: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    check_command: Mapped[str | None] = mapped_column(Text)
    tool_version_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    usage: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


def _to_skill(row: SkillRow) -> Skill:
    return Skill(
        id=row.id,
        slug=row.slug,
        owner_id=row.owner_id,
        domain=row.domain,
        status=row.status_logical,
        tags=tuple(row.tags),
        created_at=row.created_at,
        archived_at=row.archived_at,
    )


def _to_draft(row: SkillDraftRow) -> SkillDraft:
    return SkillDraft(
        id=row.id,
        skill_id=row.skill_id,
        base_version_id=row.base_version_id,
        updated_at=row.updated_at,
        lock_version=row.lock_version,
    )


def _to_version(row: SkillVersionRow) -> SkillVersion:
    return SkillVersion(
        id=row.id,
        skill_id=row.skill_id,
        semver=row.semver,
        manifest=row.manifest,
        manifest_sha256=row.manifest_sha256,
        parent_version_id=row.parent_version_id,
        status=row.status,
        changelog=row.changelog,
        author_principal_id=row.author_principal_id,
        created_at=row.created_at,
        published_at=row.published_at,
    )


class SqlAlchemySkillRepository:
    """Implémentation PostgreSQL du port Skills."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_slug(self, slug: str) -> Skill | None:
        row = (
            await self._session.execute(select(SkillRow).where(SkillRow.slug == slug))
        ).scalar_one_or_none()
        return None if row is None else _to_skill(row)

    async def list_for_owner(self, owner_id: UUID) -> list[Skill]:
        result = await self._session.execute(
            select(SkillRow)
            .where(SkillRow.owner_id == owner_id, SkillRow.archived_at.is_(None))
            .order_by(SkillRow.created_at.desc())
        )
        return [_to_skill(row) for row in result.scalars()]

    async def add_skill(self, skill: Skill) -> None:
        self._session.add(
            SkillRow(
                id=skill.id,
                slug=skill.slug,
                owner_id=skill.owner_id,
                domain=skill.domain,
                status_logical=skill.status,
                tags=list(skill.tags),
                created_at=skill.created_at,
                archived_at=skill.archived_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError(f"La Skill {skill.slug!r} existe déjà") from exc

    async def update_skill_status(self, skill_id: UUID, status: str) -> None:
        await self._session.execute(
            update(SkillRow).where(SkillRow.id == skill_id).values(status_logical=status)
        )

    async def add_draft(self, draft: SkillDraft) -> None:
        self._session.add(
            SkillDraftRow(
                id=draft.id,
                skill_id=draft.skill_id,
                base_version_id=draft.base_version_id,
                updated_at=draft.updated_at,
                lock_version=draft.lock_version,
            )
        )
        await self._session.flush()

    async def find_draft(self, skill_id: UUID) -> SkillDraft | None:
        row = (
            await self._session.execute(
                select(SkillDraftRow).where(SkillDraftRow.skill_id == skill_id)
            )
        ).scalar_one_or_none()
        return None if row is None else _to_draft(row)

    async def touch_draft(self, draft_id: UUID, updated_at: datetime) -> None:
        await self._session.execute(
            update(SkillDraftRow).where(SkillDraftRow.id == draft_id).values(updated_at=updated_at)
        )

    async def update_draft_base(
        self,
        draft_id: UUID,
        version_id: UUID,
        updated_at: datetime,
    ) -> None:
        await self._session.execute(
            update(SkillDraftRow)
            .where(SkillDraftRow.id == draft_id)
            .values(base_version_id=version_id, updated_at=updated_at)
        )

    async def store_blob(self, content: bytes) -> bytes:
        digest = sha256(content).digest()
        statement = (
            pg_insert(BlobRow)
            .values(sha256=digest, size=len(content), content=content)
            .on_conflict_do_nothing(index_elements=[BlobRow.sha256])
        )
        await self._session.execute(statement)
        return digest

    async def read_blob(self, sha256: bytes) -> bytes | None:
        row = await self._session.get(BlobRow, sha256)
        return None if row is None else row.content

    async def put_draft_file(
        self,
        draft_id: UUID,
        path: str,
        blob_sha256: bytes,
        mode: str,
    ) -> None:
        statement = (
            pg_insert(SkillDraftFileRow)
            .values(draft_id=draft_id, path=path, blob_sha256=blob_sha256, mode=mode)
            .on_conflict_do_update(
                index_elements=[SkillDraftFileRow.draft_id, SkillDraftFileRow.path],
                set_={"blob_sha256": blob_sha256, "mode": mode},
            )
        )
        await self._session.execute(statement)

    async def delete_draft_file(self, draft_id: UUID, path: str) -> None:
        await self._session.execute(
            delete(SkillDraftFileRow).where(
                SkillDraftFileRow.draft_id == draft_id,
                SkillDraftFileRow.path == path,
            )
        )

    async def list_draft_files(self, draft_id: UUID) -> list[StoredFile]:
        result = await self._session.execute(
            select(
                SkillDraftFileRow.path,
                SkillDraftFileRow.blob_sha256,
                BlobRow.size,
                SkillDraftFileRow.mode,
            )
            .join(BlobRow, BlobRow.sha256 == SkillDraftFileRow.blob_sha256)
            .where(SkillDraftFileRow.draft_id == draft_id)
            .order_by(SkillDraftFileRow.path)
        )
        return [
            StoredFile(path=path, sha256=blob_sha256, size=size, mode=mode)
            for path, blob_sha256, size, mode in result.all()
        ]

    async def add_version(
        self,
        version: SkillVersion,
        files: tuple[SkillFile, ...],
        requirements: tuple[dict[str, object], ...],
    ) -> None:
        self._session.add(
            SkillVersionRow(
                id=version.id,
                skill_id=version.skill_id,
                semver=version.semver,
                manifest=version.manifest,
                manifest_sha256=version.manifest_sha256,
                parent_version_id=version.parent_version_id,
                status=version.status,
                changelog=version.changelog,
                author_principal_id=version.author_principal_id,
                origin_kind="app",
                origin_integration_id=None,
                created_at=version.created_at,
                published_at=version.published_at,
            )
        )
        await self._session.flush()
        for file in files:
            self._session.add(
                SkillVersionFileRow(
                    version_id=version.id,
                    path=file.path,
                    blob_sha256=file.sha256,
                    size=file.size,
                    mode=file.mode,
                )
            )
        for requirement in requirements:
            self._session.add(
                SkillRequirementRow(
                    id=uuid4(),
                    skill_version_id=version.id,
                    kind=str(requirement["kind"]),
                    ecosystem=_optional_str(requirement.get("ecosystem")),
                    name=_optional_str(requirement.get("name")),
                    version_constraint=_optional_str(requirement.get("version_constraint")),
                    pinned_version=_optional_str(requirement.get("pinned_version")),
                    hashes=_optional_dict(requirement.get("hashes")),
                    check_command=_optional_str(requirement.get("check_command")),
                    tool_version_id=_optional_uuid(requirement.get("tool_version_id")),
                    usage=str(requirement.get("usage", "required")),
                    note=_optional_str(requirement.get("note")),
                )
            )
        await self._session.flush()

    async def list_versions(self, skill_id: UUID) -> list[SkillVersion]:
        result = await self._session.execute(
            select(SkillVersionRow)
            .where(SkillVersionRow.skill_id == skill_id)
            .order_by(SkillVersionRow.created_at)
        )
        return [_to_version(row) for row in result.scalars()]

    async def find_version(self, skill_id: UUID, semver: str) -> SkillVersion | None:
        row = (
            await self._session.execute(
                select(SkillVersionRow).where(
                    SkillVersionRow.skill_id == skill_id,
                    SkillVersionRow.semver == semver,
                )
            )
        ).scalar_one_or_none()
        return None if row is None else _to_version(row)

    async def list_version_files(self, version_id: UUID) -> list[StoredFile]:
        result = await self._session.execute(
            select(
                SkillVersionFileRow.path,
                SkillVersionFileRow.blob_sha256,
                SkillVersionFileRow.size,
                SkillVersionFileRow.mode,
            )
            .where(SkillVersionFileRow.version_id == version_id)
            .order_by(SkillVersionFileRow.path)
        )
        return [
            StoredFile(path=path, sha256=blob_sha256, size=size, mode=mode)
            for path, blob_sha256, size, mode in result.all()
        ]


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    typed = cast("dict[object, object]", value)
    return {str(key): item for key, item in typed.items()}


def _optional_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
