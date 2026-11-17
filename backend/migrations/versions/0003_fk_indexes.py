"""Index de couverture des clés étrangères.

Les index sont ajoutés après le schéma v0 pour éviter les parcours séquentiels lors
des vérifications de FK et des suppressions de parents.
"""

from __future__ import annotations

from alembic import op

revision: str = "0003_fk_indexes"
down_revision: str | None = "0002_audit_log_truncate_guard"
branch_labels: str | None = None
depends_on: str | None = None

_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_integration_owner_id", "integration", "(owner_id)"),
    ("ix_api_token_integration_id", "api_token", "(integration_id)"),
    ("ix_project_owner_id", "project", "(owner_id)"),
    ("ix_skill_owner_id", "skill", "(owner_id)"),
    ("ix_skill_version_parent_skill", "skill_version", "(parent_version_id, skill_id)"),
    (
        "ix_skill_version_origin_integration_id",
        "skill_version",
        "(origin_integration_id)",
    ),
    ("ix_skill_draft_base_skill", "skill_draft", "(base_version_id, skill_id)"),
    (
        "ix_skill_dependency_depends_on_skill_id",
        "skill_dependency",
        "(depends_on_skill_id)",
    ),
    ("ix_skill_deployment_version_skill", "skill_deployment", "(version_id, skill_id)"),
    ("ix_skill_deployment_skill_id", "skill_deployment", "(skill_id)"),
    (
        "ix_project_skill_pin_version_skill",
        "project_skill_pin",
        "(version_id, skill_id)",
    ),
    ("ix_project_skill_pin_skill_id", "project_skill_pin", "(skill_id)"),
    ("ix_work_plan_template_owner_id", "work_plan_template", "(owner_id)"),
    ("ix_work_plan_instance_mission_id", "work_plan_instance", "(mission_id)"),
    ("ix_work_plan_instance_project_id", "work_plan_instance", "(project_id)"),
    (
        "ix_work_plan_instance_template_version_id",
        "work_plan_instance",
        "(template_version_id)",
    ),
    ("ix_audit_log_integration_id", "audit_log", "(integration_id)"),
    (
        "ix_skill_requirement_tool_version_id",
        "skill_requirement",
        "(tool_version_id)",
    ),
    ("ix_project_technology_tool_id", "project_technology", "(tool_id)"),
    (
        "ix_project_skill_allowlist_skill_id",
        "project_skill_allowlist",
        "(skill_id)",
    ),
    (
        "ix_project_profile_snapshot_project_id",
        "project_profile_snapshot",
        "(project_id)",
    ),
)


def upgrade() -> None:
    for name, table, columns in _INDEXES:
        op.execute(f"create index if not exists {name} on {table} {columns}")


def downgrade() -> None:
    for name, _, _ in reversed(_INDEXES):
        op.execute(f"drop index if exists {name}")
