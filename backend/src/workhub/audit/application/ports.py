"""Ports du module audit."""

from __future__ import annotations

from typing import Protocol

from workhub.audit.domain.audit_entry import AuditEntry


class AuditRecorder(Protocol):
    """Écrit une entrée d'audit dans la transaction courante."""

    async def record(self, entry: AuditEntry) -> None: ...
