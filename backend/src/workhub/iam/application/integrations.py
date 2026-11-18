"""Cas d'usage de gestion des intégrations et de leurs jetons."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from workhub.iam.application.integration_ports import (
    ApiTokenFactory,
    ApiTokenRepository,
    IntegrationRepository,
)
from workhub.iam.application.views import (
    CreatedIntegrationView,
    IntegrationView,
    IssuedApiTokenView,
)
from workhub.iam.domain.api_token import ApiToken, validate_expiration, validate_scopes
from workhub.iam.domain.integration import (
    Integration,
    normalize_integration_name,
    parse_integration_kind,
)
from workhub.shared.api import (
    Clock,
    ConflictError,
    IdFactory,
    NotFoundError,
    Principal,
    new_id,
    require_scope,
)


class IntegrationService:
    """Crée, liste et révoque les intégrations d'un propriétaire."""

    def __init__(
        self,
        *,
        integrations: IntegrationRepository,
        tokens: ApiTokenRepository,
        token_factory: ApiTokenFactory,
        clock: Clock,
        id_factory: IdFactory = new_id,
    ) -> None:
        self._integrations = integrations
        self._tokens = tokens
        self._token_factory = token_factory
        self._clock = clock
        self._id_factory = id_factory

    @require_scope("integrations:manage")
    async def create(
        self,
        principal: Principal,
        *,
        name: str,
        kind: str,
        scopes: list[str],
        expires_at: datetime | None = None,
    ) -> CreatedIntegrationView:
        """Crée une intégration et son premier jeton, affiché une seule fois."""
        now = self._clock.now()
        normalized_name = normalize_integration_name(name)
        normalized_kind = parse_integration_kind(kind)
        normalized_scopes = validate_scopes(scopes)
        normalized_expiration = validate_expiration(expires_at, now)

        integration = Integration(
            id=self._id_factory(),
            name=normalized_name,
            kind=normalized_kind,
            owner_id=principal.id,
            created_at=now,
        )
        await self._integrations.add(integration)
        issued = await self._issue_token(
            integration.id,
            normalized_scopes,
            normalized_expiration,
            now,
        )
        return CreatedIntegrationView(
            integration=IntegrationView.from_integration(integration),
            token=issued,
        )

    @require_scope("integrations:manage")
    async def list(self, principal: Principal) -> list[IntegrationView]:
        """Liste les intégrations possédées par le principal."""
        integrations = await self._integrations.list_for_owner(principal.id)
        return [IntegrationView.from_integration(item) for item in integrations]

    @require_scope("integrations:manage")
    async def revoke(self, principal: Principal, integration_id: UUID) -> None:
        """Révoque une intégration et tous ses jetons, de façon idempotente."""
        integration = await self._owned_integration(principal, integration_id)
        if not integration.is_active:
            return
        now = self._clock.now()
        await self._integrations.revoke(integration.id, now)
        await self._tokens.revoke_for_integration(integration.id, now)

    @require_scope("integrations:manage")
    async def create_token(
        self,
        principal: Principal,
        integration_id: UUID,
        *,
        scopes: list[str],
        expires_at: datetime | None = None,
    ) -> IssuedApiTokenView:
        """Émet un jeton supplémentaire pour une intégration active."""
        integration = await self._owned_integration(principal, integration_id)
        if not integration.is_active:
            raise ConflictError("Intégration révoquée")
        now = self._clock.now()
        normalized_scopes = validate_scopes(scopes)
        normalized_expiration = validate_expiration(expires_at, now)
        issued = await self._issue_token(
            integration.id,
            normalized_scopes,
            normalized_expiration,
            now,
        )
        return issued

    @require_scope("integrations:manage")
    async def revoke_token(
        self,
        principal: Principal,
        integration_id: UUID,
        token_id: UUID,
    ) -> None:
        """Révoque un jeton précis, de façon idempotente."""
        integration = await self._owned_integration(principal, integration_id)
        token = await self._tokens.find_by_id(token_id)
        if token is None or token.integration_id != integration.id:
            raise NotFoundError("Jeton introuvable")
        if token.revoked_at is not None:
            return
        await self._tokens.revoke(token.id, self._clock.now())

    async def _owned_integration(
        self,
        principal: Principal,
        integration_id: UUID,
    ) -> Integration:
        integration = await self._integrations.find_by_id(integration_id)
        if integration is None or integration.owner_id != principal.id:
            raise NotFoundError("Intégration introuvable")
        return integration

    async def _issue_token(
        self,
        integration_id: UUID,
        scopes: frozenset[str],
        expires_at: datetime | None,
        now: datetime,
    ) -> IssuedApiTokenView:
        raw_token, token_hash = self._token_factory.new_token()
        token = ApiToken(
            id=self._id_factory(),
            integration_id=integration_id,
            token_sha256=token_hash,
            scopes=scopes,
            created_at=now,
            expires_at=expires_at,
        )
        await self._tokens.add(token)
        return IssuedApiTokenView.from_token(token, raw_token)
