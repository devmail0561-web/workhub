"""Ports des intégrations et de leurs jetons opaques."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from workhub.iam.domain.api_token import ApiToken
from workhub.iam.domain.integration import Integration


@dataclass(frozen=True, slots=True)
class TokenIdentity:
    """Jeton actif et intégration associée, lue dans la même requête."""

    token: ApiToken
    integration: Integration


class IntegrationRepository(Protocol):
    """Accès aux intégrations."""

    async def add(self, integration: Integration) -> None: ...

    async def find_by_id(self, integration_id: UUID) -> Integration | None: ...

    async def list_for_owner(self, owner_id: UUID) -> list[Integration]: ...

    async def revoke(self, integration_id: UUID, at: datetime) -> None: ...


class ApiTokenRepository(Protocol):
    """Accès aux jetons d'intégration."""

    async def add(self, token: ApiToken) -> None: ...

    async def find_by_id(self, token_id: UUID) -> ApiToken | None: ...

    async def find_active_by_hash(
        self,
        token_sha256: bytes,
        now: datetime,
    ) -> TokenIdentity | None: ...

    async def revoke(self, token_id: UUID, at: datetime) -> None: ...

    async def revoke_for_integration(self, integration_id: UUID, at: datetime) -> None: ...

    async def touch_last_used(self, token_id: UUID, at: datetime) -> None: ...


class ApiTokenFactory(Protocol):
    """Création, hachage et reconnaissance des jetons opaques."""

    def new_token(self) -> tuple[str, bytes]: ...

    def hash_token(self, token: str) -> bytes: ...

    def is_api_token(self, token: str) -> bool: ...
