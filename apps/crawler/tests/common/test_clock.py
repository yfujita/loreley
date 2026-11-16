from datetime import UTC, datetime, timedelta

from loreley_crawler.common.clock import SystemClock
from tests.fakes.clock import DEFAULT_NOW, FixedClock


def test_system_clock_returns_an_aware_utc_time_close_to_now() -> None:
    before = datetime.now(UTC)
    now = SystemClock().now()
    after = datetime.now(UTC)

    assert now.utcoffset() == timedelta(0)
    assert before <= now <= after


def test_fixed_clock_stays_until_it_is_advanced_or_set() -> None:
    clock = FixedClock()
    assert clock.now() == DEFAULT_NOW
    assert clock.now() == DEFAULT_NOW

    clock.advance(seconds=90)
    assert clock.now() == DEFAULT_NOW + timedelta(seconds=90)

    clock.set(DEFAULT_NOW)
    assert clock.now() == DEFAULT_NOW
