"""Pagination indépendante du framework.

`PageRequest` valide la fenêtre demandée ; `Page` transporte la fenêtre et le total. Les
couches `application` décident de la source des données, les interfaces ne font que sérialiser.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from workhub.shared.domain.errors import ValidationError

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


@dataclass(frozen=True, slots=True)
class PageRequest:
    """Fenêtre de pagination demandée (bornes validées)."""

    limit: int = DEFAULT_LIMIT
    offset: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= MAX_LIMIT:
            raise ValidationError(
                f"limit doit être comprise entre 1 et {MAX_LIMIT}",
                details={"limit": self.limit, "max": MAX_LIMIT},
            )
        if self.offset < 0:
            raise ValidationError(
                "offset doit être positif ou nul",
                details={"offset": self.offset},
            )


@dataclass(frozen=True, slots=True)
class Page[T]:
    """Fenêtre de résultats et total disponible."""

    items: tuple[T, ...]
    total: int
    limit: int
    offset: int

    def __post_init__(self) -> None:
        if self.total < 0:
            raise ValidationError("total doit être positif ou nul", details={"total": self.total})
        if not 1 <= self.limit <= MAX_LIMIT:
            raise ValidationError(
                f"limit doit être comprise entre 1 et {MAX_LIMIT}",
                details={"limit": self.limit},
            )
        if self.offset < 0:
            raise ValidationError(
                "offset doit être positif ou nul", details={"offset": self.offset}
            )

    @property
    def has_next(self) -> bool:
        """Indique s'il reste des éléments après cette fenêtre."""
        return self.offset + len(self.items) < self.total

    @property
    def next_offset(self) -> int | None:
        """Offset de la fenêtre suivante, ou `None` en fin de liste."""
        return self.offset + len(self.items) if self.has_next else None

    @classmethod
    def empty(cls, request: PageRequest) -> Page[T]:
        """Page vide respectant la fenêtre demandée."""
        return cls(items=(), total=0, limit=request.limit, offset=request.offset)


def paginate[T](items: Sequence[T], request: PageRequest, *, total: int | None = None) -> Page[T]:
    """Découpe `items` selon `request`.

    `items` doit être la séquence complète, jamais une fenêtre déjà limitée. `total` permet de
    fournir un total différent de `len(items)` (par exemple un comptage séparé) ; la fenêtre est
    toujours calculée à partir de `request.offset` et `request.limit`.
    """
    resolved_total = len(items) if total is None else total
    window = tuple(items[request.offset : request.offset + request.limit])
    return Page(items=window, total=resolved_total, limit=request.limit, offset=request.offset)
