"""Session de rafraîchissement rattachée à un utilisateur."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Session:
    """Refresh token opaque stocké sous forme de hash."""

    id: UUID
    user_id: UUID
    refresh_token_sha256: bytes
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
