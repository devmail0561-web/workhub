"""Cas d'usage de connexion, rafraîchissement et déconnexion."""

from __future__ import annotations

from datetime import datetime, timedelta

from workhub.iam.application.ports import (
    Commit,
    LoginAttemptLimiter,
    PasswordHasher,
    RefreshTokenFactory,
    SessionRepository,
    TokenIssuer,
    UserRepository,
)
from workhub.iam.application.views import AuthResult, UserView
from workhub.iam.domain.session import Session
from workhub.iam.domain.user import User, normalize_email
from workhub.shared.api import AuthenticationError, Clock, IdFactory, new_id


class AuthService:
    """Orchestre les sessions sans connaître HTTP ni SQL."""

    def __init__(
        self,
        *,
        users: UserRepository,
        sessions: SessionRepository,
        login_attempts: LoginAttemptLimiter,
        password_hasher: PasswordHasher,
        token_issuer: TokenIssuer,
        refresh_tokens: RefreshTokenFactory,
        clock: Clock,
        access_token_ttl_seconds: int,
        refresh_token_ttl_seconds: int,
        commit: Commit,
        id_factory: IdFactory = new_id,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._login_attempts = login_attempts
        self._password_hasher = password_hasher
        self._token_issuer = token_issuer
        self._refresh_tokens = refresh_tokens
        self._clock = clock
        self._access_token_ttl_seconds = access_token_ttl_seconds
        self._refresh_token_ttl_seconds = refresh_token_ttl_seconds
        self._commit = commit
        self._id_factory = id_factory

    @property
    def access_token_ttl_seconds(self) -> int:
        return self._access_token_ttl_seconds

    @property
    def refresh_token_ttl_seconds(self) -> int:
        return self._refresh_token_ttl_seconds

    async def login(self, email: str, password: str, client_ip: str) -> AuthResult:
        """Vérifie les identifiants et ouvre une session avec rotation possible."""
        normalized = normalize_email(email)
        await self._login_attempts.check(client_ip=client_ip, email=normalized)
        now = self._clock.now()
        user = await self._users.find_by_email(normalized)
        if user is None:
            await self._password_hasher.verify_dummy(password)
            await self._login_attempts.record_failure(client_ip=client_ip, email=normalized)
            raise AuthenticationError("Identifiants invalides")
        password_matches = await self._password_hasher.verify(user.password_hash, password)
        if not user.is_active or not password_matches:
            await self._login_attempts.record_failure(client_ip=client_ip, email=normalized)
            raise AuthenticationError("Identifiants invalides")

        await self._login_attempts.reset(client_ip=client_ip, email=normalized)
        raw_refresh, refresh_hash = self._refresh_tokens.new_token()
        refresh_expires_at = now + timedelta(seconds=self._refresh_token_ttl_seconds)
        await self._users.record_login(user.id, now)
        user = user.record_login(now)
        await self._sessions.create(
            Session(
                id=self._id_factory(),
                user_id=user.id,
                refresh_token_sha256=refresh_hash,
                created_at=now,
                expires_at=refresh_expires_at,
            )
        )
        await self._commit()
        return self._result(user, now, raw_refresh, refresh_expires_at)

    async def refresh(self, refresh_token: str) -> AuthResult:
        """Fait tourner le refresh token et émet un nouvel accès."""
        now = self._clock.now()
        raw_refresh, refresh_hash = self._refresh_tokens.new_token()
        refresh_expires_at = now + timedelta(seconds=self._refresh_token_ttl_seconds)
        user_id = await self._sessions.rotate(
            self._refresh_tokens.hash_token(refresh_token),
            refresh_hash,
            now,
            refresh_expires_at,
        )
        if user_id is None:
            raise AuthenticationError("Session expirée ou révoquée")

        user = await self._users.find_by_id(user_id)
        if user is None or not user.is_active:
            await self._sessions.revoke_by_hash(refresh_hash, now)
            await self._commit()
            raise AuthenticationError("Session expirée ou révoquée")
        await self._commit()
        return self._result(user, now, raw_refresh, refresh_expires_at)

    async def logout(self, refresh_token: str) -> None:
        """Révoque la session si elle existe, de façon idempotente."""
        await self._sessions.revoke_by_hash(
            self._refresh_tokens.hash_token(refresh_token),
            self._clock.now(),
        )
        await self._commit()

    async def authenticate(self, access_token: str) -> UserView:
        """Valide un JWT d'accès et retourne l'utilisateur actif."""
        user_id = self._token_issuer.decode_access_token(access_token)
        user = await self._users.find_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Jeton invalide ou expiré")
        return UserView.from_user(user)

    def _result(
        self,
        user: User,
        now: datetime,
        raw_refresh: str,
        refresh_expires_at: datetime,
    ) -> AuthResult:
        access = self._token_issuer.issue_access_token(
            user.id,
            now,
            self._access_token_ttl_seconds,
        )
        return AuthResult(
            user=UserView.from_user(user),
            access_token=access.value,
            access_expires_at=access.expires_at,
            refresh_token=raw_refresh,
            refresh_expires_at=refresh_expires_at,
        )
