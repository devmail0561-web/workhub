"""Configuration de l'authentification par variables d'environnement."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    """Réglages requis par les routes d'authentification."""

    model_config = SettingsConfigDict(env_prefix="WORKHUB_", extra="ignore")

    database_url: str = Field(validation_alias="DATABASE_URL")
    secret_key: SecretStr = Field(min_length=32)
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    refresh_token_ttl_seconds: int = Field(default=2_592_000, ge=300, le=7_776_000)
    cookie_name: str = "workhub_refresh"
    cookie_path: str = "/api/v1/auth"
    cookie_secure: bool = False


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    """Charge la configuration une seule fois par processus."""
    return AuthSettings()  # pyright: ignore[reportCallIssue]
