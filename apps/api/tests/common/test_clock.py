from datetime import UTC, datetime, timedelta

from loreley_api.common.clock import SystemClock
from tests.fakes.clock import DEFAULT_NOW, FixedClock


def test_the_system_clock_returns_an_aware_utc_time_near_now() -> None:
    before = datetime.now(UTC)

    now = SystemClock().now()

    assert now.utcoffset() == timedelta(0)
    assert before <= now <= datetime.now(UTC)


def test_the_fixed_clock_stays_until_it_is_moved() -> None:
    clock = FixedClock()

    assert clock.now() == DEFAULT_NOW
    assert clock.now() == DEFAULT_NOW
    clock.advance(seconds=60)
    assert clock.now() == DEFAULT_NOW + timedelta(seconds=60)
    clock.set(DEFAULT_NOW)
    assert clock.now() == DEFAULT_NOW
