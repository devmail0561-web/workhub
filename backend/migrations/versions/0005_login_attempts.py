"""Compteurs de tentatives de connexion par IP et par compte.

Revision ID: 0005_login_attempts
Revises: 0004_auth_sessions
Create Date: 2026-11-17
"""

from __future__ import annotations

from alembic import op

revision: str = "0005_login_attempts"
down_revision: str | None = "0004_auth_sessions"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        create table login_attempt (
            key_hash bytea primary key,
            failure_count integer not null,
            window_started_at timestamptz not null,
            locked_until timestamptz,
            updated_at timestamptz not null,
            constraint ck_login_attempt_key_taille check (octet_length(key_hash) = 32),
            constraint ck_login_attempt_compteur check (failure_count > 0),
            constraint ck_login_attempt_fenetre check (updated_at >= window_started_at)
        )
        """
    )


def downgrade() -> None:
    op.execute("drop table if exists login_attempt")
