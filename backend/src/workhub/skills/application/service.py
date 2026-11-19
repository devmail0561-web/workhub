"""Cas d'usage du module Skills."""

from __future__ import annotations

from workhub.audit.api import AuditEntry, AuditRecorder
from workhub.shared.api import (
    Clock,
    ConflictError,
    IdFactory,
    NotFoundError,
    Principal,
    ValidationError,
    new_id,
    require_scope,
)
from workhub.skills.application.ports import Commit, SkillRepository
from workhub.skills.application.views import (
    CreatedSkillView,
    DraftFileView,
    DraftView,
    SkillView,
    VersionDetailView,
    VersionView,
)
from workhub.skills.domain.skill import (
    Skill,
    SkillDraft,
    SkillFile,
    SkillVersion,
    build_manifest,
    manifest_sha256,
    semver_key,
    validate_changelog,
    validate_domain,
    validate_files,
    validate_mode,
    validate_path,
    validate_semver,
    validate_slug,
)


class SkillService:
    """Crée, édite et publie des Skills versionnées."""

    def __init__(
        self,
        *,
        skills: SkillRepository,
        audit: AuditRecorder,
        commit: Commit,
        clock: Clock,
        id_factory: IdFactory = new_id,
    ) -> None:
        self._skills = skills
        self._audit = audit
        self._commit = commit
        self._clock = clock
        self._id_factory = id_factory

    @require_scope("skills:propose")
    async def create(
        self,
        principal: Principal,
        *,
        slug: str,
        domain: str,
        files: tuple[SkillFile, ...],
        tags: tuple[str, ...] = (),
        request_id: str | None = None,
    ) -> CreatedSkillView:
        """Crée une Skill et son brouillon initial."""
        normalized_slug = validate_slug(slug)
        normalized_domain = validate_domain(domain)
        normalized_files = validate_files(files, slug=normalized_slug)
        if await self._skills.find_by_slug(normalized_slug) is not None:
            raise ConflictError(f"La Skill {normalized_slug!r} existe déjà")

        now = self._clock.now()
        skill = Skill(
            id=self._id_factory(),
            slug=normalized_slug,
            owner_id=principal.id,
            domain=normalized_domain,
            status="draft",
            tags=tags,
            created_at=now,
        )
        draft = SkillDraft(
            id=self._id_factory(),
            skill_id=skill.id,
            base_version_id=None,
            updated_at=now,
            lock_version=0,
        )
        await self._skills.add_skill(skill)
        await self._skills.add_draft(draft)
        for file in normalized_files:
            blob_sha256 = await self._skills.store_blob(file.content)
            await self._skills.put_draft_file(draft.id, file.path, blob_sha256, file.mode)
        await self._record(
            principal,
            action="skill.create",
            resource_id=str(skill.id),
            request_id=request_id,
            details={"slug": skill.slug, "domain": skill.domain, "files": len(normalized_files)},
        )
        await self._commit()
        return CreatedSkillView(
            skill=SkillView.from_skill(skill),
            draft=await self._draft_view(skill, draft),
        )

    @require_scope("skills:read")
    async def list(self, principal: Principal) -> list[SkillView]:
        """Liste les Skills dont le principal est propriétaire."""
        return [
            SkillView.from_skill(skill) for skill in await self._skills.list_for_owner(principal.id)
        ]

    @require_scope("skills:read")
    async def get(self, principal: Principal, slug: str) -> SkillView:
        """Retourne une Skill visible par le principal."""
        skill = await self._owned_skill(principal, slug)
        return SkillView.from_skill(skill)

    @require_scope("skills:read")
    async def get_draft(self, principal: Principal, slug: str) -> DraftView:
        """Retourne le brouillon et son contenu."""
        skill = await self._owned_skill(principal, slug)
        draft = await self._skills.find_draft(skill.id)
        if draft is None:
            raise NotFoundError("Brouillon introuvable")
        return await self._draft_view(skill, draft)

    @require_scope("skills:propose")
    async def put_file(
        self,
        principal: Principal,
        slug: str,
        *,
        path: str,
        content: bytes,
        mode: str = "0644",
        request_id: str | None = None,
    ) -> DraftView:
        """Crée ou remplace un fichier du brouillon."""
        skill = await self._owned_skill(principal, slug)
        draft = await self._skills.find_draft(skill.id)
        if draft is None:
            raise NotFoundError("Brouillon introuvable")
        normalized_path = validate_path(path)
        normalized_mode = validate_mode(mode)
        if len(content) > 5 * 1024 * 1024:
            raise ValidationError("Le fichier dépasse la limite de 5 Mo")
        blob_sha256 = await self._skills.store_blob(content)
        await self._skills.put_draft_file(
            draft.id,
            normalized_path,
            blob_sha256,
            normalized_mode,
        )
        now = self._clock.now()
        await self._skills.touch_draft(draft.id, now)
        updated = SkillDraft(
            id=draft.id,
            skill_id=draft.skill_id,
            base_version_id=draft.base_version_id,
            updated_at=now,
            lock_version=draft.lock_version,
        )
        await self._record(
            principal,
            action="skill.draft.file.put",
            resource_id=str(skill.id),
            request_id=request_id,
            details={"slug": skill.slug, "path": normalized_path},
        )
        await self._commit()
        return await self._draft_view(skill, updated)

    @require_scope("skills:propose")
    async def delete_file(
        self,
        principal: Principal,
        slug: str,
        *,
        path: str,
        request_id: str | None = None,
    ) -> DraftView:
        """Supprime un fichier du brouillon."""
        skill = await self._owned_skill(principal, slug)
        draft = await self._skills.find_draft(skill.id)
        if draft is None:
            raise NotFoundError("Brouillon introuvable")
        normalized_path = validate_path(path)
        if normalized_path == "SKILL.md":
            raise ValidationError("SKILL.md ne peut pas être supprimé du brouillon")
        await self._skills.delete_draft_file(draft.id, normalized_path)
        now = self._clock.now()
        await self._skills.touch_draft(draft.id, now)
        updated = SkillDraft(
            id=draft.id,
            skill_id=draft.skill_id,
            base_version_id=draft.base_version_id,
            updated_at=now,
            lock_version=draft.lock_version,
        )
        await self._record(
            principal,
            action="skill.draft.file.delete",
            resource_id=str(skill.id),
            request_id=request_id,
            details={"slug": skill.slug, "path": normalized_path},
        )
        await self._commit()
        return await self._draft_view(skill, updated)

    @require_scope("skills:publish")
    async def publish(
        self,
        principal: Principal,
        slug: str,
        *,
        semver: str,
        changelog: str,
        requirements: tuple[dict[str, object], ...] = (),
        request_id: str | None = None,
    ) -> VersionView:
        """Publie le brouillon courant comme nouvelle version immuable."""
        skill = await self._owned_skill(principal, slug)
        draft = await self._skills.find_draft(skill.id)
        if draft is None:
            raise NotFoundError("Brouillon introuvable")
        normalized_semver = validate_semver(semver)
        normalized_changelog = validate_changelog(changelog)
        stored_files = await self._skills.list_draft_files(draft.id)
        if not stored_files:
            raise ValidationError("Le brouillon est vide")
        files: list[SkillFile] = []
        for stored in stored_files:
            content = await self._skills.read_blob(stored.sha256)
            if content is None:
                raise RuntimeError(f"Blob introuvable : {stored.path}")
            files.append(SkillFile(path=stored.path, content=content, mode=stored.mode))
        normalized_files = validate_files(tuple(files), slug=skill.slug)

        versions = await self._skills.list_versions(skill.id)
        if versions:
            latest = max(versions, key=lambda item: semver_key(item.semver))
            if semver_key(normalized_semver) <= semver_key(latest.semver):
                raise ConflictError(
                    f"La version {normalized_semver} doit être supérieure à {latest.semver}"
                )
            parent = latest
        else:
            parent = None

        manifest = build_manifest(
            slug=skill.slug,
            semver=normalized_semver,
            parent=parent.semver if parent is not None else None,
            files=normalized_files,
            requirements=requirements,
        )
        now = self._clock.now()
        version = SkillVersion(
            id=self._id_factory(),
            skill_id=skill.id,
            semver=normalized_semver,
            manifest=manifest,
            manifest_sha256=manifest_sha256(manifest),
            parent_version_id=parent.id if parent is not None else None,
            status="published",
            changelog=normalized_changelog,
            author_principal_id=principal.id,
            created_at=now,
            published_at=now,
        )
        await self._skills.add_version(version, normalized_files, requirements)
        await self._skills.update_skill_status(skill.id, "published")
        await self._skills.update_draft_base(draft.id, version.id, now)
        await self._record(
            principal,
            action="skill.publish",
            resource_id=str(skill.id),
            request_id=request_id,
            details={
                "slug": skill.slug,
                "semver": version.semver,
                "manifest_sha256": version.manifest_sha256.hex(),
            },
        )
        await self._commit()
        return VersionView.from_version(
            version,
            parent_semver=parent.semver if parent is not None else None,
        )

    @require_scope("skills:read")
    async def list_versions(self, principal: Principal, slug: str) -> list[VersionView]:
        """Liste les versions publiées d'une Skill."""
        skill = await self._owned_skill(principal, slug)
        versions = await self._skills.list_versions(skill.id)
        by_id = {version.id: version.semver for version in versions}
        return [
            VersionView.from_version(
                version,
                parent_semver=(
                    by_id.get(version.parent_version_id)
                    if version.parent_version_id is not None
                    else None
                ),
            )
            for version in sorted(versions, key=lambda item: semver_key(item.semver))
        ]

    @require_scope("skills:read")
    async def get_version(
        self,
        principal: Principal,
        slug: str,
        semver: str,
    ) -> VersionDetailView:
        """Retourne une version publiée et ses métadonnées de fichiers."""
        skill = await self._owned_skill(principal, slug)
        normalized_semver = validate_semver(semver)
        version = await self._skills.find_version(skill.id, normalized_semver)
        if version is None:
            raise NotFoundError("Version introuvable")
        files = await self._skills.list_version_files(version.id)
        parent_semver = None
        if version.parent_version_id is not None:
            parent = next(
                (
                    item
                    for item in await self._skills.list_versions(skill.id)
                    if item.id == version.parent_version_id
                ),
                None,
            )
            parent_semver = parent.semver if parent is not None else None
        return VersionDetailView(
            version=VersionView.from_version(version, parent_semver=parent_semver),
            files=tuple(files),
            manifest=version.manifest,
        )

    async def _owned_skill(self, principal: Principal, slug: str) -> Skill:
        skill = await self._skills.find_by_slug(validate_slug(slug))
        if skill is None or (skill.owner_id != principal.id and not principal.has_scope("*")):
            raise NotFoundError("Skill introuvable")
        return skill

    async def _draft_view(self, skill: Skill, draft: SkillDraft) -> DraftView:
        files: list[DraftFileView] = []
        for stored in await self._skills.list_draft_files(draft.id):
            content = await self._skills.read_blob(stored.sha256)
            if content is None:
                raise RuntimeError(f"Blob introuvable : {stored.path}")
            files.append(
                DraftFileView(
                    path=stored.path,
                    content=content,
                    mode=stored.mode,
                    sha256=stored.sha256,
                    size=stored.size,
                )
            )
        return DraftView(
            skill=SkillView.from_skill(skill),
            lock_version=draft.lock_version,
            updated_at=draft.updated_at,
            files=tuple(sorted(files, key=lambda item: item.path)),
        )

    async def _record(
        self,
        principal: Principal,
        *,
        action: str,
        resource_id: str,
        request_id: str | None,
        details: dict[str, object],
    ) -> None:
        await self._audit.record(
            AuditEntry(
                principal_type=principal.type.value,
                principal_id=principal.id,
                integration_id=(principal.id if principal.type.value == "integration" else None),
                action=action,
                resource_type="skill",
                resource_id=resource_id,
                request_id=request_id,
                outcome="success",
                details=details,
            )
        )
