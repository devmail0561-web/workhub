"""Persistance PostgreSQL du journal d'audit."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Identity, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from workhub.audit.domain.audit_entry import AuditEntry
from workhub.shared.infrastructure.database import Base


class AuditLogRow(Base):
    """Ligne append-only de la table `audit_log`."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    principal_type: Mapped[str] = mapped_column(Text, nullable=False)
    principal_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    integration_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class SqlAlchemyAuditRecorder:
    """Écrit les entrées dans la session et la transaction de l'appelant."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, entry: AuditEntry) -> None:
        self._session.add(
            AuditLogRow(
                principal_type=entry.principal_type,
                principal_id=entry.principal_id,
                integration_id=entry.integration_id,
                action=entry.action,
                resource_type=entry.resource_type,
                resource_id=entry.resource_id,
                request_id=entry.request_id,
                outcome=entry.outcome,
                details=entry.details,
            )
        )
        await self._session.flush()
