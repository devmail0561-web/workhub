"""Principal : identité unifiée des humains, intégrations et tâches système."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from workhub.shared.domain.errors import PermissionDeniedError


class PrincipalType(StrEnum):
    """Nature du principal authentifié."""

    USER = "user"
    INTEGRATION = "integration"
    SYSTEM = "system"


def _scope_matches(granted: str, required: str) -> bool:
    if granted == "*" or granted == required:
        return True
    return granted.endswith(":*") and required.startswith(granted[:-1])


@dataclass(frozen=True, slots=True)
class Principal:
    """Identité autorisée, indépendante du mécanisme d'authentification.

    `scopes` contient des habilitations de la forme `skills:read`. Le joker `*` accorde tout,
    et `skills:*` accorde toutes les actions de la ressource `skills`.
    """

    id: UUID
    type: PrincipalType
    display_name: str | None = None
    scopes: frozenset[str] = frozenset()
    owner_user_id: UUID | None = None

    @classmethod
    def system(cls, name: str = "system") -> Principal:
        """Principal des tâches internes (amorçage, maintenance)."""
        return cls(
            id=UUID(int=0), type=PrincipalType.SYSTEM, display_name=name, scopes=frozenset({"*"})
        )

    def has_scope(self, required: str) -> bool:
        """Indique si le principal possède le scope demandé."""
        return any(_scope_matches(granted, required) for granted in self.scopes)

    def require_scope(self, required: str) -> None:
        """Lève `PermissionDeniedError` si le scope demandé est absent."""
        if not self.has_scope(required):
            raise PermissionDeniedError(
                f"Scope requis : {required}",
                details={
                    "required_scope": required,
                    "principal_type": self.type.value,
                    "principal_id": str(self.id),
                },
            )
