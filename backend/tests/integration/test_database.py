from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

pytestmark = pytest.mark.integration

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

FK_INDEXES = {
    "ix_integration_owner_id",
    "ix_api_token_integration_id",
    "ix_project_owner_id",
    "ix_skill_owner_id",
    "ix_skill_version_parent_skill",
    "ix_skill_version_origin_integration_id",
    "ix_skill_draft_base_skill",
    "ix_skill_dependency_depends_on_skill_id",
    "ix_skill_deployment_version_skill",
    "ix_skill_deployment_skill_id",
    "ix_project_skill_pin_version_skill",
    "ix_project_skill_pin_skill_id",
    "ix_work_plan_template_owner_id",
    "ix_work_plan_instance_mission_id",
    "ix_work_plan_instance_project_id",
    "ix_work_plan_instance_template_version_id",
    "ix_audit_log_integration_id",
    "ix_skill_requirement_tool_version_id",
    "ix_project_technology_tool_id",
    "ix_project_skill_allowlist_skill_id",
    "ix_project_profile_snapshot_project_id",
    "ix_session_user_id",
}


async def test_migration_is_applied(session: AsyncSession) -> None:
    version = (await session.execute(text("select version_num from alembic_version"))).scalar_one()

    assert version == "0004_auth_sessions"


async def test_key_tables_exist(session: AsyncSession) -> None:
    for name in ("skill", "blob", "audit_log", "work_plan_instance", "proposal", "session"):
        found = (
            await session.execute(text("select to_regclass(:name)"), {"name": f"public.{name}"})
        ).scalar_one()
        assert found == name


async def test_app_user_has_admin_flag(session: AsyncSession) -> None:
    column = (
        await session.execute(
            text(
                "select data_type from information_schema.columns "
                "where table_name = 'app_user' and column_name = 'is_admin'"
            )
        )
    ).scalar_one()

    assert column == "boolean"


async def test_immutability_triggers_are_installed(session: AsyncSession) -> None:
    count = (
        await session.execute(text("select count(*) from pg_trigger where not tgisinternal"))
    ).scalar_one()

    assert count >= 17


async def test_fk_covering_indexes_exist(session: AsyncSession) -> None:
    names = (
        await session.execute(text("select indexname from pg_indexes where schemaname = 'public'"))
    ).scalars()

    assert set(names) >= FK_INDEXES


async def test_blob_hash_is_enforced(session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await session.execute(
            text("insert into blob (sha256, size, content) values (digest('a', 'sha256'), 1, 'b')")
        )
    await session.rollback()


async def test_audit_log_is_append_only(session: AsyncSession) -> None:
    await session.execute(
        text(
            "insert into audit_log (principal_type, action, resource_type, outcome) "
            "values ('system', 'test', 'test', 'success')"
        )
    )

    with pytest.raises(IntegrityError):
        await session.execute(text("update audit_log set action = 'forged'"))

    await session.rollback()


async def test_audit_log_cannot_be_truncated(session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await session.execute(text("truncate audit_log"))

    await session.rollback()


async def test_schema_verification_script_passes(engine: AsyncEngine) -> None:
    script = (REPOSITORY_ROOT / "docs" / "specs" / "schema-v0.verify.sql").read_text(
        encoding="utf-8"
    )
    without_psql_meta = "\n".join(
        line for line in script.splitlines() if not line.lstrip().startswith("\\")
    )

    async with engine.connect() as connection:
        await connection.exec_driver_sql(without_psql_meta)
