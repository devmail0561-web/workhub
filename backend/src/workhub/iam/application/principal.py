"""Résolution d'un Principal à partir d'une session ou d'un jeton d'intégration."""

from __future__ import annotations

from workhub.iam.application.integration_ports import (
    ApiTokenFactory,
    ApiTokenRepository,
)
from workhub.iam.application.ports import Commit, TokenIssuer, UserRepository
from workhub.iam.application.views import UserView
from workhub.shared.api import (
    AuthenticationError,
    Clock,
    Principal,
    PrincipalType,
)


class PrincipalResolver:
    """Transforme un identifiant Bearer en Principal autorisé."""

    def __init__(
        self,
        *,
        users: UserRepository,
        tokens: ApiTokenRepository,
        token_issuer: TokenIssuer,
        token_factory: ApiTokenFactory,
        commit: Commit,
        clock: Clock,
    ) -> None:
        self._users = users
        self._tokens = tokens
        self._token_issuer = token_issuer
        self._token_factory = token_factory
        self._commit = commit
        self._clock = clock

    async def resolve(self, credential: str) -> Principal:
        """Résout un jeton d'intégration opaque ou un JWT d'accès utilisateur."""
        now = self._clock.now()
        if self._token_factory.is_api_token(credential):
            identity = await self._tokens.find_active_by_hash(
                self._token_factory.hash_token(credential),
                now,
            )
            if identity is None:
                raise AuthenticationError("Jeton invalide ou expiré")
            await self._tokens.touch_last_used(identity.token.id, now)
            await self._commit()
            return Principal(
                id=identity.integration.id,
                type=PrincipalType.INTEGRATION,
                display_name=identity.integration.name,
                scopes=identity.token.scopes,
            )

        user_id = self._token_issuer.decode_access_token(credential)
        user = await self._users.find_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Jeton invalide ou expiré")
        return UserView.from_user(user).to_principal()
