"""Interdit TRUNCATE sur audit_log.

Le trigger v0 protège les mutations ligne par ligne (`UPDATE`/`DELETE`). `TRUNCATE`
ne déclenche pas ces triggers : cette migration ajoute un trigger statement-level
pour conserver l'append-only même pour un rôle propriétaire.
"""

from __future__ import annotations

from alembic import op

revision: str = "0002_audit_log_truncate_guard"
down_revision: str | None = "0001_schema_v0"
branch_labels: str | None = None
depends_on: str | None = None

_TRIGGER = "trg_audit_log_no_truncate"


def upgrade() -> None:
    op.execute(f"drop trigger if exists {_TRIGGER} on audit_log")
    op.execute(
        f"create trigger {_TRIGGER} before truncate on audit_log "
        "for each statement execute function workhub_reject_mutation()"
    )


def downgrade() -> None:
    op.execute(f"drop trigger if exists {_TRIGGER} on audit_log")
