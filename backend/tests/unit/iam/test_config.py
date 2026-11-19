from __future__ import annotations

from typing import Literal

import pytest
from pydantic import SecretStr

from workhub.iam.infrastructure.config import AuthSettings


def _settings(
    *,
    database_url: str = "postgresql+psycopg://workhub_app:strong@localhost:5432/workhub",
    secret_key: str = "a" * 48,
    environment: Literal["development", "test", "production"] = "development",
    cookie_secure: bool = False,
) -> AuthSettings:
    return AuthSettings(
        database_url=database_url,
        secret_key=SecretStr(secret_key),
        environment=environment,
        cookie_secure=cookie_secure,
    )


def test_production_rejects_example_secret_and_database_password() -> None:
    with pytest.raises(ValueError, match="valeur d'exemple"):
        _settings(
            environment="production",
            cookie_secure=True,
            secret_key="change-me-change-me-change-me-32chars",
        )
    with pytest.raises(ValueError, match="mot de passe d'exemple"):
        _settings(
            environment="production",
            cookie_secure=True,
            database_url="postgresql+psycopg://workhub_app:change-me-app@localhost:5432/workhub",
        )


def test_production_requires_a_secure_cookie() -> None:
    with pytest.raises(ValueError, match="WORKHUB_COOKIE_SECURE"):
        _settings(environment="production", cookie_secure=False)

    settings = _settings(environment="production", cookie_secure=True)
    assert settings.cookie_secure is True


def test_reads_workhub_environment_and_trusted_proxies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKHUB_ENV", "test")
    monkeypatch.delenv("WORKHUB_ENVIRONMENT", raising=False)
    settings = AuthSettings(
        database_url="postgresql+psycopg://workhub_app:strong@localhost:5432/workhub",
        secret_key=SecretStr("a" * 48),
    )
    assert settings.environment == "test"

    monkeypatch.setenv("WORKHUB_TRUSTED_PROXIES", "172.28.0.10")
    settings = AuthSettings(
        database_url="postgresql+psycopg://workhub_app:strong@localhost:5432/workhub",
        secret_key=SecretStr("a" * 48),
    )
    assert settings.trusted_proxies == "172.28.0.10"


def test_development_allows_http_cookies_and_examples() -> None:
    settings = _settings(
        environment="development",
        cookie_secure=False,
        secret_key="change-me-change-me-change-me-32chars",
    )
    assert settings.cookie_secure is False
