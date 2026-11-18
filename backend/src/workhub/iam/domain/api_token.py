"""Jetons d'intégration opaques et validation des scopes."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from workhub.shared.api import ValidationError

API_TOKEN_PREFIX = "whub_"
_MAX_SCOPES = 50
_SCOPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$")
_FORBIDDEN_SCOPES = frozenset(
    {
        "integrations:manage",
        "projects:delete",
        "skills:publish",
        "tools:publish",
    }
)


def validate_scopes(scopes: Iterable[str]) -> frozenset[str]:
    """Valide les scopes d'un jeton d'intégration.

    Les jokers et les droits humains par défaut sont refusés : un jeton reste limité à des
    actions explicites. Les doublons sont éliminés.
    """
    normalized = frozenset(scope.strip() for scope in scopes)
    if not normalized:
        raise ValidationError("Au moins un scope est requis")
    if len(normalized) > _MAX_SCOPES:
        raise ValidationError(f"Un jeton ne peut porter plus de {_MAX_SCOPES} scopes")
    for scope in normalized:
        if not _SCOPE_PATTERN.fullmatch(scope):
            raise ValidationError(f"Scope invalide : {scope!r}")
        if scope in _FORBIDDEN_SCOPES:
            raise ValidationError(f"Scope réservé aux sessions humaines : {scope}")
    return normalized


def validate_expiration(expires_at: datetime | None, now: datetime) -> datetime | None:
    """Vérifie qu'une expiration, si fournie, est consciente du fuseau et dans le futur."""
    if expires_at is None:
        return None
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        raise ValidationError("La date d'expiration doit inclure un fuseau horaire")
    if expires_at <= now:
        raise ValidationError("La date d'expiration doit être dans le futur")
    return expires_at


@dataclass(frozen=True, slots=True)
class ApiToken:
    """Jeton opaque dont seul le hash SHA-256 est persisté."""

    id: UUID
    integration_id: UUID
    token_sha256: bytes
    scopes: frozenset[str]
    created_at: datetime
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    def is_active(self, at: datetime) -> bool:
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > at)

    def revoke(self, at: datetime) -> ApiToken:
        if self.revoked_at is not None:
            return self
        return replace(self, revoked_at=at)
