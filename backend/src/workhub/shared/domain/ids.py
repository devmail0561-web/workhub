"""Génération d'identifiants.

Les identifiants sont des UUID v4 générés en application, avant l'écriture en base : les cas
d'usage peuvent ainsi construire un agrégat complet et rester indépendants du stockage.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

#: Fabrique d'identifiants injectable (utile pour des tests déterministes).
IdFactory = Callable[[], UUID]


def new_id() -> UUID:
    """Retourne un nouvel UUID v4."""
    return uuid4()
