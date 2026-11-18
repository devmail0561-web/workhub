"""Dépendances d'authentification communes aux routes REST."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from workhub.iam.api import Principal, PrincipalResolver, get_principal_resolver
from workhub.shared.api import AuthenticationError

_bearer = HTTPBearer(auto_error=False)


async def current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    resolver: Annotated[PrincipalResolver, Depends(get_principal_resolver)],
) -> Principal:
    """Résout le Principal d'une requête Bearer (session ou jeton d'intégration)."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Jeton d'accès absent")
    return await resolver.resolve(credentials.credentials)
