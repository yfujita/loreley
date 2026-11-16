"""`scheduler` の設定。値は仮値で、設定可能(`config.py` が詰める)。"""

from dataclasses import dataclass
from datetime import UTC, tzinfo


@dataclass(frozen=True)
class SchedulerSettings:
    """既定値は実装者の仮値(architecture 11章の「Scheduler の判定周期」は空欄。CM-U-6)。

    - `check_interval_seconds`: 定期起動の判定のために起きる周期。長いほど、起動が期限より遅れうる
      (最大でこの秒数)。短いほど、ソース一覧とジョブ記録の読み取りが増える。cron 式の最小の単位
      (1 分)に対して十分短い 30 秒を仮置きする。
    - `timezone`: `schedule_cron` を解釈するタイムゾーン(全ソース共通。既定は UTC)。
    """

    check_interval_seconds: float = 30.0
    timezone: tzinfo = UTC

    def __post_init__(self) -> None:
        if self.check_interval_seconds <= 0:
            raise ValueError("check_interval_seconds must be positive")
