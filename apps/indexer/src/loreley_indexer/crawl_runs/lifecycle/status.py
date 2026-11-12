"""Status API の応答の組み立て(arch 9.5、api 4.5。K43)。

削除結果だけを返す(登録結果と確認結果の区分は含まない)。「削除中」は `status` に加えず、
判定中・実行中も `status=running` のまま。進捗は `deletion_started_at` と、実際に記録済みの
`deleted_count` で見る(未記録の進捗は推測して返さない)。
"""

from dataclasses import dataclass
from datetime import datetime

from loreley_indexer.common.errors import CrawlNotFoundError
from loreley_indexer.crawl_runs.lifecycle.records import (
    DeletionReason,
    DeletionResultRecord,
    DeletionStatus,
)
from loreley_indexer.crawl_runs.lifecycle.results import DeletionResults


@dataclass(frozen=True)
class CrawlStatus:
    """api 4.5 の応答の項目。値のないものは None(api 層が JSON から省く)。"""

    crawl_id: str
    source_id: str
    status: DeletionStatus
    reason: DeletionReason | None
    forced: bool
    target_count: int | None
    denominator: int | None
    ttl: int
    ratio_threshold: float
    min_delete_count: int
    deleted_count: int | None
    enumerated_count: int | None
    n_seen: int | None
    e_missing: int | None
    finish_received_at: datetime | None
    deletion_started_at: datetime | None
    finished_at: datetime | None  # 結果が終端状態になった時刻
    waiting_for: str | None  # 待機中のみ。直前に先行する削除結果の `crawl_id`(案)


class StatusReader:
    def __init__(self, results: DeletionResults) -> None:
        self._results = results

    def read(self, crawl_id: str) -> CrawlStatus:
        """結果がなければ `CrawlNotFoundError`(404。消えた・開始通知がない・喪失を区別しない)。"""
        stored = self._results.fetch_result(crawl_id)
        if stored is None:
            raise CrawlNotFoundError
        record = stored.record
        return CrawlStatus(
            crawl_id=record.crawl_id,
            source_id=record.source_id,
            status=record.status,
            reason=record.reason,
            forced=record.forced,
            target_count=record.target_count,
            denominator=record.denominator,
            ttl=record.ttl,
            ratio_threshold=record.ratio_threshold,
            min_delete_count=record.min_delete_count,
            deleted_count=record.deleted_count,
            enumerated_count=record.enumerated_count,
            n_seen=record.n_seen,
            e_missing=record.e_missing,
            finish_received_at=record.finish_received_at,
            deletion_started_at=record.deletion_started_at,
            finished_at=record.ended_at,
            waiting_for=self._waiting_for(record),
        )

    def _waiting_for(self, record: DeletionResultRecord) -> str | None:
        """終了通知を受理済みで `running` のうち、先行する結果があるものだけ(待機中)。"""
        if record.status is not DeletionStatus.RUNNING:
            return None
        preceding = self._results.preceding_results(record)
        return preceding[-1].crawl_id if preceding else None
