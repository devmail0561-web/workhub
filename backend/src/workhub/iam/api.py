"""API publique du module iam.

Seul point d'entrée autorisé pour les autres modules (règle §3.3-3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from workhub.audit.infrastructure.repositories import SqlAlchemyAuditRecorder
from workhub.iam.application.auth import AuthService
from workhub.iam.application.integrations import IntegrationService
from workhub.iam.application.ports import AccessToken
from workhub.iam.application.principal import PrincipalResolver
from workhub.iam.application.views import (
    AuthResult,
    CreatedIntegrationView,
    IntegrationView,
    IssuedApiTokenView,
    UserView,
)
from workhub.iam.infrastructure.config import AuthSettings, get_auth_settings
from workhub.iam.infrastructure.database import create_engine, create_session_factory
from workhub.iam.infrastructure.repositories import (
    SqlAlchemyApiTokenRepository,
    SqlAlchemyIntegrationRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
)
from workhub.iam.infrastructure.security import (
    Argon2PasswordHasher,
    JwtTokenIssuer,
    OpaqueApiTokenFactory,
    OpaqueRefreshTokenFactory,
)
from workhub.iam.infrastructure.throttle import SqlAlchemyLoginAttemptLimiter
from workhub.shared.api import Principal, SystemClock

__all__ = [
    "AccessToken",
    "AuthResult",
    "AuthService",
    "AuthSettings",
    "CookieSettings",
    "CreatedIntegrationView",
    "IntegrationService",
    "IntegrationView",
    "IssuedApiTokenView",
    "Principal",
    "PrincipalResolver",
    "UserView",
    "get_auth_service",
    "get_cookie_settings",
    "get_integration_service",
    "get_principal_resolver",
    "get_session_factory",
]


@dataclass(frozen=True, slots=True)
class CookieSettings:
    """Paramètres du cookie de rafraîchissement, sans secret."""

    name: str
    path: str
    secure: bool


@lru_cache(maxsize=1)
def _engine_for_url(database_url: str) -> AsyncEngine:
    return create_engine(database_url)


@lru_cache(maxsize=1)
def _session_factory_for_url(database_url: str) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(_engine_for_url(database_url))


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Retourne la fabrique de sessions liée à `DATABASE_URL`."""
    settings = get_auth_settings()
    return _session_factory_for_url(settings.database_url)


def get_cookie_settings() -> CookieSettings:
    """Retourne les paramètres du cookie de rafraîchissement."""
    settings = get_auth_settings()
    return CookieSettings(
        name=settings.cookie_name,
        path=settings.cookie_path,
        secure=settings.cookie_secure,
    )


async def get_auth_service() -> AsyncIterator[AuthService]:
    """Compose le service d'authentification et gère la transaction de la requête."""
    settings = get_auth_settings()
    factory = get_session_factory()
    async with factory() as session:
        service = AuthService(
            users=SqlAlchemyUserRepository(session),
            sessions=SqlAlchemySessionRepository(session),
            login_attempts=SqlAlchemyLoginAttemptLimiter(
                factory,
                SystemClock(),
                max_attempts=settings.login_max_attempts,
                window_seconds=settings.login_attempt_window_seconds,
                lock_seconds=settings.login_lock_seconds,
            ),
            password_hasher=Argon2PasswordHasher(),
            token_issuer=JwtTokenIssuer(settings.secret_key.get_secret_value()),
            refresh_tokens=OpaqueRefreshTokenFactory(),
            clock=SystemClock(),
            access_token_ttl_seconds=settings.access_token_ttl_seconds,
            refresh_token_ttl_seconds=settings.refresh_token_ttl_seconds,
            commit=session.commit,
        )
        try:
            yield service
        except Exception:
            await session.rollback()
            raise


async def get_integration_service() -> AsyncIterator[IntegrationService]:
    """Compose le service d'intégration et gère la transaction de la requête."""
    factory = get_session_factory()
    async with factory() as session:
        service = IntegrationService(
            integrations=SqlAlchemyIntegrationRepository(session),
            tokens=SqlAlchemyApiTokenRepository(session),
            token_factory=OpaqueApiTokenFactory(),
            audit=SqlAlchemyAuditRecorder(session),
            commit=session.commit,
            clock=SystemClock(),
        )
        try:
            yield service
        except Exception:
            await session.rollback()
            raise


async def get_principal_resolver() -> AsyncIterator[PrincipalResolver]:
    """Compose la résolution d'identité et gère la transaction de la requête."""
    settings = get_auth_settings()
    factory = get_session_factory()
    async with factory() as session:
        resolver = PrincipalResolver(
            users=SqlAlchemyUserRepository(session),
            tokens=SqlAlchemyApiTokenRepository(session),
            token_issuer=JwtTokenIssuer(settings.secret_key.get_secret_value()),
            token_factory=OpaqueApiTokenFactory(),
            commit=session.commit,
            clock=SystemClock(),
        )
        try:
            yield resolver
        except Exception:
            await session.rollback()
            raise
