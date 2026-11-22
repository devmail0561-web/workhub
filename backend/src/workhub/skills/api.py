"""API publique du module skills.

Seul point d'entrée autorisé pour les autres modules (règle §3.3-3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from workhub.audit.infrastructure.repositories import SqlAlchemyAuditRecorder
from workhub.iam.api import get_session_factory
from workhub.shared.api import Principal, SystemClock
from workhub.skills.application.service import SkillService
from workhub.skills.application.views import (
    CreatedSkillView,
    DraftFileView,
    DraftView,
    FileDiffView,
    SkillView,
    VersionDetailView,
    VersionDiffView,
    VersionHistoryView,
    VersionLogEntryView,
    VersionView,
)
from workhub.skills.domain.skill import DiffStats, SkillFile, StoredFile
from workhub.skills.infrastructure.repositories import SqlAlchemySkillRepository

__all__ = [
    "CreatedSkillView",
    "DiffStats",
    "DraftFileView",
    "DraftView",
    "FileDiffView",
    "Principal",
    "SkillFile",
    "SkillService",
    "SkillView",
    "StoredFile",
    "VersionDetailView",
    "VersionDiffView",
    "VersionHistoryView",
    "VersionLogEntryView",
    "VersionView",
    "get_skill_service",
]


async def get_skill_service() -> AsyncIterator[SkillService]:
    """Compose le service Skills et gère la transaction de la requête."""
    factory = get_session_factory()
    async with factory() as session:
        service = SkillService(
            skills=SqlAlchemySkillRepository(session),
            audit=SqlAlchemyAuditRecorder(session),
            commit=session.commit,
            clock=SystemClock(),
        )
        try:
            yield service
        except Exception:
            await session.rollback()
            raise
