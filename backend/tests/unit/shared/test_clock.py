from datetime import UTC, datetime, timedelta

from workhub.shared.api import SystemClock


def test_system_clock_returns_aware_utc() -> None:
    before = datetime.now(UTC)
    now = SystemClock().now()
    after = datetime.now(UTC)

    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)
    assert before <= now <= after
