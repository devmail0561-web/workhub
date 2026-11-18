"""Intégrations : environnements et agents autorisés."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from workhub.shared.api import ValidationError


class IntegrationKind(StrEnum):
    """Type d'environnement connecté."""

    OPENCODE = "opencode"
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    OTHER = "other"


_MAX_NAME_LENGTH = 200


def normalize_integration_name(name: str) -> str:
    """Retourne un nom non vide et borné."""
    normalized = name.strip()
    if not 1 <= len(normalized) <= _MAX_NAME_LENGTH:
        raise ValidationError(
            f"Le nom de l'intégration doit contenir entre 1 et {_MAX_NAME_LENGTH} caractères"
        )
    return normalized


def parse_integration_kind(kind: str) -> IntegrationKind:
    """Convertit un type texte en énumération validée."""
    try:
        return IntegrationKind(kind)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in IntegrationKind)
        raise ValidationError(f"Type d'intégration invalide ; attendu : {allowed}") from exc


@dataclass(frozen=True, slots=True)
class Integration:
    """Environnement connecté appartenant à un utilisateur."""

    id: UUID
    name: str
    kind: IntegrationKind
    owner_id: UUID
    created_at: datetime
    revoked_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def revoke(self, at: datetime) -> Integration:
        """Retourne l'intégration révoquée, sans modifier l'historique."""
        if self.revoked_at is not None:
            return self
        return replace(self, revoked_at=at)
