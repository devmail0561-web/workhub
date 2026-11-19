"""Configuration de l'authentification par variables d'environnement."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRET_MARKERS = ("change-me", "changeme", "replace-me", "example-secret")


class AuthSettings(BaseSettings):
    """Réglages requis par les routes d'authentification."""

    model_config = SettingsConfigDict(env_prefix="WORKHUB_", extra="ignore", populate_by_name=True)

    database_url: str = Field(validation_alias="DATABASE_URL")
    secret_key: SecretStr = Field(min_length=32)
    environment: Literal["development", "test", "production"] = Field(
        default="production", validation_alias="WORKHUB_ENV"
    )
    trusted_proxies: str = "127.0.0.1"
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    refresh_token_ttl_seconds: int = Field(default=2_592_000, ge=300, le=7_776_000)
    login_max_attempts: int = Field(default=5, ge=2, le=100)
    login_attempt_window_seconds: int = Field(default=900, ge=60, le=86_400)
    login_lock_seconds: int = Field(default=900, ge=60, le=86_400)
    cookie_name: str = "workhub_refresh"
    cookie_path: str = "/api/v1/auth"
    cookie_secure: bool = False

    @model_validator(mode="after")
    def _reject_insecure_defaults(self) -> AuthSettings:
        if self.environment != "production":
            return self
        secret = self.secret_key.get_secret_value().lower()
        if any(marker in secret for marker in _INSECURE_SECRET_MARKERS):
            raise ValueError("WORKHUB_SECRET_KEY utilise une valeur d'exemple")
        if "change-me" in self.database_url.lower():
            raise ValueError("DATABASE_URL utilise un mot de passe d'exemple")
        if not self.cookie_secure:
            raise ValueError("WORKHUB_COOKIE_SECURE doit être true en production")
        return self


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    """Charge la configuration une seule fois par processus."""
    return AuthSettings()  # pyright: ignore[reportCallIssue]
