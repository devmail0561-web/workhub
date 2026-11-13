"""Schéma initial v0.

Le DDL de référence est `docs/specs/schema-v0.sql`. Une copie est conservée sous
`migrations/sql/` pour que la migration soit autonome ; un test garantit l'égalité des deux
fichiers. Ce DDL sera remplacé par des migrations incrémentales dès E1.
"""

from __future__ import annotations

from pathlib import Path

from alembic import op
from migrations.sql_split import split_sql

revision: str = "0001_schema_v0"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

_SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "0001_schema_v0.sql"

_TABLES = (
    "project_profile_snapshot",
    "proposal",
    "project_convention",
    "project_skill_allowlist",
    "project_technology",
    "skill_requirement",
    "tool_version_file",
    "tool_version",
    "tool",
    "audit_log",
    "execution_record",
    "instance_node",
    "work_plan_instance",
    "work_plan_version",
    "work_plan_template",
    "project_skill_pin",
    "skill_deployment",
    "skill_dependency",
    "skill_version_file",
    "skill_draft_file",
    "skill_draft",
    "skill_version",
    "blob",
    "skill",
    "mission",
    "project",
    "api_token",
    "integration",
    "app_user",
)

_FUNCTIONS = (
    "workhub_dependency_guard",
    "workhub_snapshot_guard",
    "workhub_proposal_guard",
    "workhub_instance_guard",
    "workhub_work_plan_version_guard",
    "workhub_version_guard",
    "workhub_blob_guard",
    "workhub_touch_updated_at",
    "workhub_reject_mutation",
)


def _statements() -> list[str]:
    statements = split_sql(_SQL_PATH.read_text(encoding="utf-8"))
    return [
        statement
        for statement in statements
        if statement.strip().lower() not in {"begin", "commit"}
    ]


def upgrade() -> None:
    for statement in _statements():
        op.execute(statement)


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"drop table if exists {table} cascade")
    for function in _FUNCTIONS:
        op.execute(f"drop function if exists {function}() cascade")
