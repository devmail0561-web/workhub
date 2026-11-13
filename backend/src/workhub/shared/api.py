"""API publique du module shared.

Seul point d'entrée autorisé pour les autres modules (règles d'architecture 3, 6 et 7).
"""

from workhub.shared.domain.clock import Clock, SystemClock
from workhub.shared.domain.errors import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    PreconditionFailedError,
    RateLimitedError,
    ValidationError,
    WorkHubError,
)
from workhub.shared.domain.ids import IdFactory, new_id
from workhub.shared.domain.pagination import Page, PageRequest, paginate
from workhub.shared.domain.principal import Principal, PrincipalType

__all__ = [
    "AuthenticationError",
    "Clock",
    "ConflictError",
    "IdFactory",
    "NotFoundError",
    "Page",
    "PageRequest",
    "PermissionDeniedError",
    "PreconditionFailedError",
    "Principal",
    "PrincipalType",
    "RateLimitedError",
    "SystemClock",
    "ValidationError",
    "WorkHubError",
    "new_id",
    "paginate",
]
