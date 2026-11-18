"""Décorateur d'autorisation pour les cas d'usage de la couche application."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from workhub.shared.domain.principal import Principal

P = ParamSpec("P")
R = TypeVar("R")


def require_scope(
    scope: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Exige un scope sur le `Principal` reçu par le cas d'usage décoré.

    Le principal doit être passé en argument nommé `principal` ou positionnel. L'interface
    résout l'identité ; l'application décide seule des permissions.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            principal = kwargs.get("principal")
            if not isinstance(principal, Principal):
                principal = next(
                    (argument for argument in args if isinstance(argument, Principal)),
                    None,
                )
            if principal is None:
                raise TypeError("Le cas d'usage décoré doit recevoir un Principal")
            principal.require_scope(scope)
            return await func(*args, **kwargs)

        return wrapper

    return decorator
