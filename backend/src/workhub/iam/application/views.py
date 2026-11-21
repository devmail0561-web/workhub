"""Représentations publiques de l'authentification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from workhub.iam.domain.api_token import ApiToken
from workhub.iam.domain.integration import Integration
from workhub.iam.domain.user import User
from workhub.shared.api import Principal, PrincipalType


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

    def to_principal(self) -> Principal:
        """Convertit le compte en Principal avec les droits humains par défaut."""
        if self.is_admin:
            scopes = frozenset({"*"})
        else:
            scopes = frozenset({"skills:read", "skills:propose", "skills:publish"})
        return Principal(
            id=self.id,
            type=PrincipalType.USER,
            display_name=self.display_name,
            scopes=scopes,
            owner_user_id=self.id,
        )


@dataclass(frozen=True, slots=True)
class AuthResult:
    """Jetons et identité renvoyés par une connexion ou un rafraîchissement."""

    user: UserView
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


@dataclass(frozen=True, slots=True)
class IntegrationView:
    """Intégration exposable, sans secret."""

    id: UUID
    name: str
    kind: str
    owner_id: UUID
    created_at: datetime
    revoked_at: datetime | None

    @classmethod
    def from_integration(cls, integration: Integration) -> IntegrationView:
        return cls(
            id=integration.id,
            name=integration.name,
            kind=integration.kind.value,
            owner_id=integration.owner_id,
            created_at=integration.created_at,
            revoked_at=integration.revoked_at,
        )


@dataclass(frozen=True, slots=True)
class IssuedApiTokenView:
    """Jeton affiché une seule fois, accompagné de ses métadonnées."""

    id: UUID
    token: str
    scopes: frozenset[str]
    expires_at: datetime | None

    @classmethod
    def from_token(cls, token: ApiToken, raw_token: str) -> IssuedApiTokenView:
        return cls(
            id=token.id,
            token=raw_token,
            scopes=token.scopes,
            expires_at=token.expires_at,
        )


@dataclass(frozen=True, slots=True)
class CreatedIntegrationView:
    """Intégration et premier jeton renvoyés ensemble à la création."""

    integration: IntegrationView
    token: IssuedApiTokenView
