"""`jobs` 直下(受付・解放・回復・Job Runner)の設定。値は仮値で、設定可能(`config.py` が詰める)。

`owner` は、実行している Crawler の安定した ID(architecture 5.1・CA-P-3。再起動の前後で同じ値)。
ロック文書とジョブ記録の `owner` に書き、起動時の回復が「自分のもの」を見分けるのに使う。
Indexer がロック文書の `owner` を 256 バイト以内・制御文字なしで検証するため、同じ規則で検査する。
"""

import unicodedata
from dataclasses import dataclass, field

from loreley_crawler.jobs.locks import HeartbeatSettings

OWNER_MAX_BYTES = 256


@dataclass(frozen=True)
class JobsSettings:
    """既定値は architecture 11章の仮値。空欄の項目(走査間隔)は実装者の仮値(5 秒)。

    - `runner_scan_interval_seconds`: Job Runner が、起床通知を取りこぼしたときにも `queued` を
      見つけるための走査間隔(CM-U-6)
    - `admitting_lock_grace_seconds`: ジョブ記録のないロックのうち、`acquired_at` がこの秒数以内の
      ものは、受付の途中とみなして解放しない(architecture 5.4・11章。60 秒)
    """

    owner: str
    heartbeat: HeartbeatSettings = field(default_factory=HeartbeatSettings)
    runner_scan_interval_seconds: float = 5.0
    admitting_lock_grace_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not self.owner:
            raise ValueError("owner must not be empty")
        # 孤児サロゲートを含む値は UTF-8 にできず、`UnicodeEncodeError`(`ValueError`)で拒否する。
        if len(self.owner.encode("utf-8")) > OWNER_MAX_BYTES:
            raise ValueError(f"owner must be at most {OWNER_MAX_BYTES} bytes in UTF-8")
        if any(unicodedata.category(character) == "Cc" for character in self.owner):
            raise ValueError("owner must not contain control characters")
        if self.runner_scan_interval_seconds <= 0:
            raise ValueError("runner_scan_interval_seconds must be positive")
        if self.admitting_lock_grace_seconds <= 0:
            raise ValueError("admitting_lock_grace_seconds must be positive")
