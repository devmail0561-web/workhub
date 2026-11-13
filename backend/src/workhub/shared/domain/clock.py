"""Horloge injectable.

Le domaine ne lit jamais l'heure système directement : il reçoit un `Clock`, ce qui rend les
règles temporelles testables et déterministes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Source de temps injectable."""

    def now(self) -> datetime:
        """Retourne un instant **timezone-aware** en UTC."""
        ...


class SystemClock:
    """Horloge réelle, en UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)
