"""Adaptation du moteur partagé pour le module IAM."""

from __future__ import annotations

from workhub.shared.infrastructure.database import (
    Base,
    create_engine,
    create_session_factory,
)

__all__ = ["Base", "create_engine", "create_session_factory"]
