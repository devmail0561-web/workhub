"""Garde-fous des intégrations et de leurs jetons.

Revision ID: 0006_integrations
Revises: 0005_login_attempts
Create Date: 2026-11-18
"""

from __future__ import annotations

from alembic import op

revision: str = "0006_integrations"
down_revision: str | None = "0005_login_attempts"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        alter table integration
            add constraint ck_integration_kind
            check (kind in ('opencode', 'claude_code', 'codex', 'other'))
        """
    )
    op.execute(
        """
        alter table api_token
            add constraint ck_api_token_expiration
            check (expires_at is null or expires_at > created_at)
        """
    )


def downgrade() -> None:
    op.execute("alter table api_token drop constraint if exists ck_api_token_expiration")
    op.execute("alter table integration drop constraint if exists ck_integration_kind")
