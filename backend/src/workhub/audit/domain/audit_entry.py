"""Entrée du journal d'audit append-only."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

PrincipalType = Literal["user", "integration", "system"]
Outcome = Literal["success", "failure", "denied"]


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """Événement métier à journaliser, sans secret."""

    principal_type: PrincipalType
    principal_id: UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    outcome: Outcome
    integration_id: UUID | None = None
    request_id: str | None = None
    details: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
