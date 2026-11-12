from abc import ABC, abstractmethod
from datetime import UTC, datetime


class Clock(ABC):
    """現在時刻の取得元。テストで固定時計に差し替えるために抽象化する。"""

    @abstractmethod
    def now(self) -> datetime:
        """タイムゾーン付き(UTC)の現在時刻を返す。"""


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)
