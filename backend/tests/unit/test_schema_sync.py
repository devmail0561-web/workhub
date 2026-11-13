from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent


def test_vendored_schema_matches_reference() -> None:
    reference = (REPOSITORY_ROOT / "docs" / "specs" / "schema-v0.sql").read_text(encoding="utf-8")
    vendored = (BACKEND_ROOT / "migrations" / "sql" / "0001_schema_v0.sql").read_text(
        encoding="utf-8"
    )

    assert vendored == reference
