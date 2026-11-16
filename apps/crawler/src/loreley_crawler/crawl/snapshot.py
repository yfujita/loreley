"""設定スナップショット(architecture 3.3.1・7.4。CA-K-5)。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from loreley_crawler.common.timestamps import format_instant


@dataclass(frozen=True)
class SettingsSnapshot:
    """ジョブごとに、`running` への遷移の直後に 1 度だけ組み立てる 6 項目。

    開始通知・`last-seen`・バッチ登録は、すべてこの値から送る(再送のたびに設定を読み直さない)。
    `crawl_started_at` は `started_at` と同じ時刻。`datetime` のまま持てば、どの要請でも同じ文字列
    になる(`format_instant` は決定的)。型は strict に送る(`indexer_client` が検査する。7.4)。
    """

    crawl_started_at: datetime
    ttl: int
    ratio_threshold: float
    min_delete_count: int
    force_delete: bool
    rewrite_mode: bool

    def to_record(self) -> dict[str, Any]:
        """ジョブ記録の `settings_snapshot`(JSON の型。ちょうど 6 項目)。"""
        return {
            "crawl_started_at": format_instant(self.crawl_started_at),
            "ttl": self.ttl,
            "ratio_threshold": self.ratio_threshold,
            "min_delete_count": self.min_delete_count,
            "force_delete": self.force_delete,
            "rewrite_mode": self.rewrite_mode,
        }
