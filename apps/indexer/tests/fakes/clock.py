from datetime import UTC, datetime, timedelta

from loreley_indexer.common.clock import Clock

DEFAULT_NOW = datetime(2026, 11, 11, 0, 0, 0, tzinfo=UTC)


class FixedClock(Clock):
    """進めない限り同じ時刻を返す。スリープに頼らずに期限切れなどを再現する。"""

    def __init__(self, now: datetime = DEFAULT_NOW) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        self._now = now

    def advance(self, *, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
