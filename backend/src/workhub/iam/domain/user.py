"""Utilisateur et règles de normalisation d'identité."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from workhub.shared.api import ValidationError

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_EMAIL_LENGTH = 320
_MAX_DISPLAY_NAME_LENGTH = 200
_MIN_PASSWORD_LENGTH = 12
_MAX_PASSWORD_LENGTH = 1024


def normalize_email(email: str) -> str:
    """Retourne l'e-mail normalisé (espaces retirés, minuscules) ou lève une erreur."""
    normalized = email.strip().lower()
    if len(normalized) > _MAX_EMAIL_LENGTH or not _EMAIL_PATTERN.fullmatch(normalized):
        raise ValidationError("Adresse e-mail invalide")
    return normalized


def validate_password(password: str) -> None:
    """Vérifie la politique minimale du mot de passe d'amorçage."""
    if not _MIN_PASSWORD_LENGTH <= len(password) <= _MAX_PASSWORD_LENGTH:
        raise ValidationError(
            "Le mot de passe doit contenir entre "
            f"{_MIN_PASSWORD_LENGTH} et {_MAX_PASSWORD_LENGTH} caractères"
        )


@dataclass(frozen=True, slots=True)
class User:
    """Compte humain authentifiable."""

    id: UUID
    email: str
    password_hash: str
    display_name: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None

    def record_login(self, at: datetime) -> User:
        """Retourne le même utilisateur avec la date de dernière connexion mise à jour."""
        return replace(self, last_login_at=at, updated_at=at)
