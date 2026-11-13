import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_migration_is_applied(session: AsyncSession) -> None:
    version = (await session.execute(text("select version_num from alembic_version"))).scalar_one()

    assert version == "0001_schema_v0"


async def test_key_tables_exist(session: AsyncSession) -> None:
    for name in ("skill", "blob", "audit_log", "work_plan_instance", "proposal"):
        found = (
            await session.execute(text("select to_regclass(:name)"), {"name": f"public.{name}"})
        ).scalar_one()
        assert found == name


async def test_immutability_triggers_are_installed(session: AsyncSession) -> None:
    count = (
        await session.execute(text("select count(*) from pg_trigger where not tgisinternal"))
    ).scalar_one()

    assert count >= 16


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
