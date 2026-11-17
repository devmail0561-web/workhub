"""Représentations publiques de l'authentification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from workhub.iam.domain.user import User


@dataclass(frozen=True, slots=True)
class UserView:
    """Utilisateur exposable à une interface, sans hash de mot de passe."""

    id: UUID
    email: str
    display_name: str
    is_admin: bool
    last_login_at: datetime | None

    @classmethod
    def from_user(cls, user: User) -> UserView:
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_admin=user.is_admin,
            last_login_at=user.last_login_at,
        )


@dataclass(frozen=True, slots=True)
class AuthResult:
    """Jetons et identité renvoyés par une connexion ou un rafraîchissement."""

    user: UserView
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
