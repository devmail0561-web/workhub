"""Erreurs métier partagées.

Les erreurs ne connaissent pas HTTP : la traduction en statut et en enveloppe JSON est faite
par la couche `interfaces.rest` (voir `workhub.interfaces.rest.errors`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar


class WorkHubError(Exception):
    """Erreur métier de base, porteuse d'un code stable et de détails."""

    code: ClassVar[str] = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details: Mapping[str, object] = dict(details or {})

    def __str__(self) -> str:
        return self.message


class ValidationError(WorkHubError):
    """Donnée invalide (format, borne, cohérence)."""

    code = "validation_error"


class AuthenticationError(WorkHubError):
    """Authentification absente ou invalide."""

    code = "authentication_required"


class PermissionDeniedError(WorkHubError):
    """Principal authentifié mais scope ou droit insuffisant."""

    code = "permission_denied"


class NotFoundError(WorkHubError):
    """Ressource inexistante ou non visible."""

    code = "not_found"


class ConflictError(WorkHubError):
    """Conflit d'état (unicité, transition interdite)."""

    code = "conflict"


class PreconditionFailedError(WorkHubError):
    """Précondition d'écriture invalide (`If-Match`, verrou optimiste)."""

    code = "precondition_failed"


class RateLimitedError(WorkHubError):
    """Trop de tentatives ou quota dépassé."""

    code = "rate_limited"
