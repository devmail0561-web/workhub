"""Sessions de rafraîchissement et indicateur administrateur.

Revision ID: 0004_auth_sessions
Revises: 0003_fk_indexes
Create Date: 2026-11-17
"""

from __future__ import annotations

from alembic import op

revision: str = "0004_auth_sessions"
down_revision: str | None = "0003_fk_indexes"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("alter table app_user add column is_admin boolean not null default false")
    op.execute(
        """
        create table "session" (
            id uuid primary key,
            user_id uuid not null references app_user (id) on delete cascade,
            refresh_token_sha256 bytea not null,
            created_at timestamptz not null,
            expires_at timestamptz not null,
            last_used_at timestamptz,
            revoked_at timestamptz,
            constraint ck_session_hash_taille check (octet_length(refresh_token_sha256) = 32),
            constraint ck_session_expiration check (expires_at > created_at)
        )
        """
    )
    op.execute('create unique index ux_session_refresh_hash on "session" (refresh_token_sha256)')
    op.execute('create index ix_session_user_id on "session" (user_id)')
    op.execute('create index ix_session_expires_at on "session" (expires_at)')


def downgrade() -> None:
    op.execute('drop table if exists "session"')
    op.execute("alter table app_user drop column if exists is_admin")
