"""Cas d'usage du module Skills."""

from __future__ import annotations

from dataclasses import replace
from typing import cast
from uuid import UUID

from workhub.audit.api import AuditEntry, AuditRecorder
from workhub.shared.api import (
    Clock,
    ConflictError,
    IdFactory,
    NotFoundError,
    PermissionDeniedError,
    PreconditionFailedError,
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
    FileDiffView,
    ResolvedDependencyView,
    SkillView,
    VersionDetailView,
    VersionDiffView,
    VersionHistoryView,
    VersionLogEntryView,
    VersionView,
)
from workhub.skills.domain.skill import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_VERSION_BYTES,
    ResolvedDependency,
    Skill,
    SkillDependency,
    SkillDraft,
    SkillFile,
    SkillVersion,
    build_manifest,
    diff_files,
    manifest_sha256,
    normalize_dependencies,
    normalize_requirements,
    satisfies_constraint,
    semver_key,
    skill_metadata,
    summarize_diff,
    validate_changelog,
    validate_constraint,
    validate_domain,
    validate_files,
    validate_mode,
    validate_path,
    validate_semver,
    validate_skill_transition,
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
            owner_id=self._principal_owner_id(principal),
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
        """Liste les Skills visibles : les siennes et toutes les versions publiées."""
        owner_id = principal.owner_user_id or principal.id
        skills = await self._skills.list_visible(
            owner_id,
            include_all=principal.has_scope("*"),
        )
        return [SkillView.from_skill(skill) for skill in skills]

    @require_scope("skills:read")
    async def get(self, principal: Principal, slug: str) -> SkillView:
        """Retourne une Skill visible par le principal."""
        skill = await self._visible_skill(principal, slug)
        return SkillView.from_skill(skill)

    @require_scope("skills:publish")
    async def transition(
        self,
        principal: Principal,
        slug: str,
        *,
        target_status: str,
        request_id: str | None = None,
    ) -> SkillView:
        """Applique une transition autorisée du cycle de vie de la Skill."""
        skill = await self._owned_skill(principal, slug)
        target = validate_skill_transition(skill.status, target_status)
        archived_at = self._clock.now() if target == "archived" else None
        await self._skills.update_skill_status(skill.id, target, archived_at)
        await self._record(
            principal,
            action="skill.transition",
            resource_id=str(skill.id),
            request_id=request_id,
            details={"slug": skill.slug, "from": skill.status, "to": target},
        )
        await self._commit()
        return SkillView.from_skill(replace(skill, status=target, archived_at=archived_at))

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
        expected_lock_version: int | None = None,
        request_id: str | None = None,
    ) -> DraftView:
        """Crée ou remplace un fichier du brouillon sous précondition ETag."""
        skill = await self._owned_skill(principal, slug)
        self._ensure_mutable(skill)
        draft = await self._skills.find_draft(skill.id)
        if draft is None:
            raise NotFoundError("Brouillon introuvable")
        normalized_path = validate_path(path)
        normalized_mode = validate_mode(mode)
        if len(content) > MAX_FILE_BYTES:
            raise ValidationError(f"Le fichier dépasse la limite de {MAX_FILE_BYTES} octets")

        stored_files = await self._skills.list_draft_files(draft.id)
        existing = next((item for item in stored_files if item.path == normalized_path), None)
        total = sum(item.size for item in stored_files if item.path != normalized_path)
        total += len(content)
        if total > MAX_VERSION_BYTES:
            raise ValidationError(f"Un brouillon ne peut pas dépasser {MAX_VERSION_BYTES} octets")
        if existing is None and len(stored_files) >= MAX_FILES:
            raise ValidationError(f"Un brouillon ne peut pas contenir plus de {MAX_FILES} fichiers")

        expected = draft.lock_version if expected_lock_version is None else expected_lock_version
        now = self._clock.now()
        if not await self._skills.touch_draft(draft.id, expected, now):
            raise PreconditionFailedError("Le brouillon a été modifié entre-temps")
        blob_sha256 = await self._skills.store_blob(content)
        await self._skills.put_draft_file(
            draft.id,
            normalized_path,
            blob_sha256,
            normalized_mode,
        )
        updated = SkillDraft(
            id=draft.id,
            skill_id=draft.skill_id,
            base_version_id=draft.base_version_id,
            updated_at=now,
            lock_version=expected + 1,
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
        expected_lock_version: int | None = None,
        request_id: str | None = None,
    ) -> DraftView:
        """Supprime un fichier du brouillon sous précondition ETag."""
        skill = await self._owned_skill(principal, slug)
        self._ensure_mutable(skill)
        draft = await self._skills.find_draft(skill.id)
        if draft is None:
            raise NotFoundError("Brouillon introuvable")
        normalized_path = validate_path(path)
        if normalized_path == "SKILL.md":
            raise ValidationError("SKILL.md ne peut pas être supprimé du brouillon")
        expected = draft.lock_version if expected_lock_version is None else expected_lock_version
        now = self._clock.now()
        if not await self._skills.touch_draft(draft.id, expected, now):
            raise PreconditionFailedError("Le brouillon a été modifié entre-temps")
        await self._skills.delete_draft_file(draft.id, normalized_path)
        updated = SkillDraft(
            id=draft.id,
            skill_id=draft.skill_id,
            base_version_id=draft.base_version_id,
            updated_at=now,
            lock_version=expected + 1,
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
        dependencies: tuple[dict[str, object], ...] = (),
        expected_lock_version: int | None = None,
        request_id: str | None = None,
    ) -> VersionView:
        """Publie le brouillon courant comme nouvelle version immuable."""
        skill = await self._owned_skill(principal, slug)
        self._ensure_mutable(skill)
        draft = await self._skills.find_draft(skill.id)
        if draft is None:
            raise NotFoundError("Brouillon introuvable")
        normalized_semver = validate_semver(semver)
        normalized_changelog = validate_changelog(changelog)
        normalized_requirements = normalize_requirements(requirements)
        normalized_dependencies = normalize_dependencies(dependencies)
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
        metadata = skill_metadata(normalized_files, slug=skill.slug)

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

        resolved_dependencies = await self._resolve_dependencies(skill, normalized_dependencies)
        manifest = build_manifest(
            slug=skill.slug,
            name=metadata.name,
            description=metadata.description,
            semver=normalized_semver,
            parent=parent.semver if parent is not None else None,
            files=normalized_files,
            requirements=normalized_requirements,
            dependencies=tuple(
                {
                    "slug": dependency.slug,
                    "constraint": dependency.constraint,
                    "resolved_semver": dependency.semver,
                }
                for dependency in resolved_dependencies
            ),
        )
        now = self._clock.now()
        expected = draft.lock_version if expected_lock_version is None else expected_lock_version
        if expected != draft.lock_version:
            raise PreconditionFailedError("Le brouillon a été modifié entre-temps")
        origin_kind = "integration" if principal.type.value == "integration" else "app"
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
            origin_kind=origin_kind,
            origin_integration_id=(principal.id if origin_kind == "integration" else None),
        )
        await self._skills.add_version(
            version,
            normalized_files,
            normalized_requirements,
            resolved_dependencies,
        )
        if not await self._skills.update_draft_base(draft.id, version.id, expected, now):
            raise PreconditionFailedError("Le brouillon a été modifié entre-temps")
        await self._skills.update_skill_status(skill.id, "published")
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

    @require_scope("skills:publish")
    async def rollback(
        self,
        principal: Principal,
        slug: str,
        *,
        from_semver: str,
        semver: str,
        changelog: str,
        expected_lock_version: int | None = None,
        request_id: str | None = None,
    ) -> VersionView:
        """Publie une nouvelle version à partir du contenu d'une version antérieure."""
        skill = await self._owned_skill(principal, slug)
        self._ensure_mutable(skill)
        source = await self._find_version(skill.id, from_semver)
        normalized_semver = validate_semver(semver)
        normalized_changelog = validate_changelog(changelog)
        draft = await self._skills.find_draft(skill.id)
        if draft is None:
            raise NotFoundError("Brouillon introuvable")

        versions = await self._skills.list_versions(skill.id)
        latest = max(versions, key=lambda item: semver_key(item.semver), default=None)
        if latest is not None and semver_key(normalized_semver) <= semver_key(latest.semver):
            raise ConflictError(
                f"La version {normalized_semver} doit être supérieure à {latest.semver}"
            )

        source_files = await self._version_files(source)
        requirements = _manifest_requirements(source.manifest)
        dependency_payloads = _manifest_dependency_payloads(source.manifest)
        resolved_dependencies = await self._resolve_manifest_dependencies(dependency_payloads)
        for dependency in resolved_dependencies:
            await self._assert_no_cycle(skill.id, dependency, (skill.slug,), set())
        metadata = skill_metadata(source_files, slug=skill.slug)
        manifest = build_manifest(
            slug=skill.slug,
            name=metadata.name,
            description=metadata.description,
            semver=normalized_semver,
            parent=latest.semver if latest is not None else None,
            files=source_files,
            requirements=requirements,
            dependencies=dependency_payloads,
        )

        expected = draft.lock_version if expected_lock_version is None else expected_lock_version
        if expected != draft.lock_version:
            raise PreconditionFailedError("Le brouillon a été modifié entre-temps")
        now = self._clock.now()
        origin_kind = "integration" if principal.type.value == "integration" else "app"
        version = SkillVersion(
            id=self._id_factory(),
            skill_id=skill.id,
            semver=normalized_semver,
            manifest=manifest,
            manifest_sha256=manifest_sha256(manifest),
            parent_version_id=latest.id if latest is not None else None,
            status="published",
            changelog=normalized_changelog,
            author_principal_id=principal.id,
            created_at=now,
            published_at=now,
            origin_kind=origin_kind,
            origin_integration_id=(principal.id if origin_kind == "integration" else None),
        )
        await self._skills.add_version(
            version,
            source_files,
            requirements,
            resolved_dependencies,
        )

        stored_source = await self._skills.list_version_files(source.id)
        source_paths = {stored.path for stored in stored_source}
        for stored in await self._skills.list_draft_files(draft.id):
            if stored.path not in source_paths:
                await self._skills.delete_draft_file(draft.id, stored.path)
        for stored in stored_source:
            await self._skills.put_draft_file(
                draft.id,
                stored.path,
                stored.sha256,
                stored.mode,
            )
        if not await self._skills.update_draft_base(draft.id, version.id, expected, now):
            raise PreconditionFailedError("Le brouillon a été modifié entre-temps")
        await self._skills.update_skill_status(skill.id, "published")
        await self._record(
            principal,
            action="skill.rollback",
            resource_id=str(skill.id),
            request_id=request_id,
            details={
                "slug": skill.slug,
                "from_semver": source.semver,
                "semver": version.semver,
                "manifest_sha256": version.manifest_sha256.hex(),
            },
        )
        await self._commit()
        return VersionView.from_version(
            version,
            parent_semver=latest.semver if latest is not None else None,
        )

    @require_scope("skills:read")
    async def list_versions(self, principal: Principal, slug: str) -> list[VersionView]:
        """Liste les versions publiées d'une Skill visible."""
        skill = await self._visible_skill(principal, slug)
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
        skill = await self._visible_skill(principal, slug)
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
            dependencies=_manifest_dependencies(version.manifest),
        )

    @require_scope("skills:read")
    async def diff(
        self,
        principal: Principal,
        slug: str,
        *,
        from_semver: str,
        to_semver: str,
    ) -> VersionDiffView:
        """Compare deux versions publiées d'une Skill visible."""
        skill = await self._visible_skill(principal, slug)
        source = await self._find_version(skill.id, from_semver)
        target = await self._find_version(skill.id, to_semver)
        diffs = diff_files(
            await self._version_files(source),
            await self._version_files(target),
        )
        return VersionDiffView(
            slug=skill.slug,
            from_semver=source.semver,
            to_semver=target.semver,
            files=tuple(FileDiffView.from_diff(diff) for diff in diffs),
        )

    @require_scope("skills:read")
    async def history(self, principal: Principal, slug: str) -> VersionHistoryView:
        """Retrace l'historique des versions, du plus récent au plus ancien."""
        skill = await self._visible_skill(principal, slug)
        versions = await self._skills.list_versions(skill.id)
        by_id = {version.id: version for version in versions}
        semver_by_id = {version.id: version.semver for version in versions}
        cache: dict[UUID, tuple[SkillFile, ...]] = {}
        entries: list[VersionLogEntryView] = []
        for version in sorted(
            versions,
            key=lambda item: semver_key(item.semver),
            reverse=True,
        ):
            parent = (
                by_id.get(version.parent_version_id)
                if version.parent_version_id is not None
                else None
            )
            before = await self._version_files(parent, cache) if parent is not None else ()
            after = await self._version_files(version, cache)
            entries.append(
                VersionLogEntryView(
                    id=version.id,
                    semver=version.semver,
                    parent_semver=(
                        semver_by_id.get(version.parent_version_id)
                        if version.parent_version_id is not None
                        else None
                    ),
                    status=version.status,
                    changelog=version.changelog,
                    author_principal_id=version.author_principal_id,
                    manifest_sha256=version.manifest_sha256,
                    origin_kind=version.origin_kind,
                    origin_integration_id=version.origin_integration_id,
                    created_at=version.created_at,
                    published_at=version.published_at,
                    changes=summarize_diff(diff_files(before, after)),
                )
            )
        return VersionHistoryView(
            slug=skill.slug,
            head=entries[0].semver if entries else None,
            versions=tuple(entries),
        )

    async def _resolve_dependencies(
        self,
        skill: Skill,
        dependencies: tuple[SkillDependency, ...],
    ) -> tuple[ResolvedDependency, ...]:
        resolved: list[ResolvedDependency] = []
        for dependency in dependencies:
            if dependency.slug == skill.slug:
                raise ValidationError("Une Skill ne peut pas dépendre d'elle-même")
            target = await self._skills.find_by_slug(dependency.slug)
            if target is None or target.status not in {"published", "deprecated"}:
                raise ValidationError(f"Dépendance introuvable ou non publiée : {dependency.slug}")
            version = await self._highest_satisfying(target.id, dependency.constraint)
            if version is None:
                raise ConflictError(
                    f"Aucune version de {dependency.slug!r} ne satisfait {dependency.constraint!r}"
                )
            resolved.append(
                ResolvedDependency(
                    slug=dependency.slug,
                    constraint=dependency.constraint,
                    skill_id=target.id,
                    version_id=version.id,
                    semver=version.semver,
                )
            )
        for dependency in resolved:
            await self._assert_no_cycle(skill.id, dependency, (skill.slug,), set())
        return tuple(resolved)

    async def _highest_satisfying(
        self,
        skill_id: UUID,
        constraint: str,
    ) -> SkillVersion | None:
        versions = await self._skills.list_versions(skill_id)
        candidates = [
            version
            for version in versions
            if version.status == "published" and satisfies_constraint(version.semver, constraint)
        ]
        return max(candidates, key=lambda item: semver_key(item.semver), default=None)

    async def _resolve_manifest_dependencies(
        self,
        dependencies: tuple[dict[str, object], ...],
    ) -> tuple[ResolvedDependency, ...]:
        resolved: list[ResolvedDependency] = []
        for payload in dependencies:
            slug = validate_slug(_manifest_text(payload, "slug"))
            constraint = validate_constraint(_manifest_text(payload, "constraint"))
            semver = validate_semver(_manifest_text(payload, "resolved_semver"))
            target = await self._skills.find_by_slug(slug)
            if target is None:
                raise ConflictError(f"Dépendance introuvable : {slug}")
            version = await self._skills.find_version(target.id, semver)
            if version is None:
                raise ConflictError(f"Version de dépendance introuvable : {slug}@{semver}")
            resolved.append(
                ResolvedDependency(
                    slug=slug,
                    constraint=constraint,
                    skill_id=target.id,
                    version_id=version.id,
                    semver=semver,
                )
            )
        return tuple(resolved)

    async def _assert_no_cycle(
        self,
        root_skill_id: UUID,
        dependency: ResolvedDependency,
        path: tuple[str, ...],
        visited: set[UUID],
    ) -> None:
        if dependency.skill_id == root_skill_id:
            raise ValidationError("Cycle de dépendances : " + " -> ".join((*path, dependency.slug)))
        if dependency.version_id in visited:
            return
        visited.add(dependency.version_id)
        for declared in await self._skills.list_version_dependencies(dependency.version_id):
            target = await self._skills.find_by_slug(declared.slug)
            if target is None:
                continue
            if target.id == root_skill_id:
                raise ValidationError(
                    "Cycle de dépendances : " + " -> ".join((*path, dependency.slug, declared.slug))
                )
            version = await self._highest_satisfying(target.id, declared.constraint)
            if version is None:
                continue
            await self._assert_no_cycle(
                root_skill_id,
                ResolvedDependency(
                    slug=declared.slug,
                    constraint=declared.constraint,
                    skill_id=target.id,
                    version_id=version.id,
                    semver=version.semver,
                ),
                (*path, dependency.slug),
                visited,
            )

    async def _find_version(self, skill_id: UUID, semver: str) -> SkillVersion:
        version = await self._skills.find_version(skill_id, validate_semver(semver))
        if version is None:
            raise NotFoundError("Version introuvable")
        return version

    async def _version_files(
        self,
        version: SkillVersion,
        cache: dict[UUID, tuple[SkillFile, ...]] | None = None,
    ) -> tuple[SkillFile, ...]:
        if cache is not None and version.id in cache:
            return cache[version.id]
        files: list[SkillFile] = []
        for stored in await self._skills.list_version_files(version.id):
            content = await self._skills.read_blob(stored.sha256)
            if content is None:
                raise RuntimeError(f"Blob introuvable : {stored.path}")
            files.append(SkillFile(path=stored.path, content=content, mode=stored.mode))
        result = tuple(files)
        if cache is not None:
            cache[version.id] = result
        return result

    def _principal_owner_id(self, principal: Principal) -> UUID:
        if principal.type.value == "integration":
            if principal.owner_user_id is None:
                raise PermissionDeniedError(
                    "L'intégration ne possède pas de propriétaire utilisateur"
                )
            return principal.owner_user_id
        return principal.owner_user_id or principal.id

    async def _owned_skill(self, principal: Principal, slug: str) -> Skill:
        skill = await self._skills.find_by_slug(validate_slug(slug))
        owner_id = self._principal_owner_id(principal)
        if skill is None or (skill.owner_id != owner_id and not principal.has_scope("*")):
            raise NotFoundError("Skill introuvable")
        return skill

    def _ensure_mutable(self, skill: Skill) -> None:
        if skill.status == "archived":
            raise ConflictError("Une Skill archivée est en lecture seule")

    async def _visible_skill(self, principal: Principal, slug: str) -> Skill:
        skill = await self._skills.find_by_slug(validate_slug(slug))
        if skill is None:
            raise NotFoundError("Skill introuvable")
        owner_id = principal.owner_user_id or principal.id
        if skill.owner_id == owner_id or principal.has_scope("*"):
            return skill
        if skill.status in {"published", "deprecated"}:
            return skill
        raise NotFoundError("Skill introuvable")

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


def _manifest_requirements(manifest: dict[str, object]) -> tuple[dict[str, object], ...]:
    raw = manifest.get("requirements")
    if not isinstance(raw, list):
        return ()
    return tuple(
        cast("dict[str, object]", item)
        for item in cast("list[object]", raw)
        if isinstance(item, dict)
    )


def _manifest_dependency_payloads(
    manifest: dict[str, object],
) -> tuple[dict[str, object], ...]:
    raw = manifest.get("dependencies")
    if not isinstance(raw, list):
        return ()
    return tuple(
        cast("dict[str, object]", item)
        for item in cast("list[object]", raw)
        if isinstance(item, dict)
    )


def _manifest_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConflictError(f"Manifeste de dépendance invalide : champ {key} manquant")
    return value


def _manifest_dependencies(
    manifest: dict[str, object],
) -> tuple[ResolvedDependencyView, ...]:
    raw = manifest.get("dependencies")
    if not isinstance(raw, list):
        return ()
    dependencies: list[ResolvedDependencyView] = []
    for item in cast("list[object]", raw):
        if not isinstance(item, dict):
            continue
        entry = cast("dict[str, object]", item)
        slug = entry.get("slug")
        constraint = entry.get("constraint")
        resolved_semver = entry.get("resolved_semver")
        if (
            isinstance(slug, str)
            and isinstance(constraint, str)
            and isinstance(resolved_semver, str)
        ):
            dependencies.append(
                ResolvedDependencyView(
                    slug=slug,
                    constraint=constraint,
                    resolved_semver=resolved_semver,
                )
            )
    return tuple(dependencies)
