"""開始通知の受理(arch 9.5、9.9、api 4.1)。

判定の順序(設計書の順。変えない):
1. 同じ `crawl_id` の結果が終端状態 → 409 `crawl_already_finished`
2. 同じ `crawl_id` で `running` → 複写済みの項目と直接比較。一致なら状態を変えず成功(再送)、
   1 つでも違えば 409 `crawl_start_conflict`
3. `crawl_started_at` が現行世代より古い → 409 `stale_crawl_started_at`

通ったときの書き込みの順は、世代の更新 → 旧い結果の `superseded` 化 → 新しい結果の作成。
結果の作成を最後(コミット点)にして、途中で失敗して Crawler が再送しても、
再送が「結果あり=成功」で世代の更新や整理を飛ばさないようにする。
受理済みの旧い削除(待機中・判定中・実行中)は止めず、`discarded` にもしない。
"""

from datetime import datetime

from loreley_indexer.common.clock import Clock
from loreley_indexer.common.errors import (
    CrawlAlreadyFinishedError,
    CrawlStartConflictError,
    StaleCrawlStartedAtError,
)
from loreley_indexer.common.source_locks import SourceLocks
from loreley_indexer.common.timestamps import format_instant
from loreley_indexer.crawl_runs.lifecycle.config import LifecycleConfig
from loreley_indexer.crawl_runs.lifecycle.notifications import StartNotification
from loreley_indexer.crawl_runs.lifecycle.records import (
    DeletionReason,
    DeletionRecord,
    DeletionResultRecord,
    DeletionStatus,
)
from loreley_indexer.crawl_runs.lifecycle.results import (
    DeletionResults,
    retry_after_conflict,
)
from loreley_indexer.infrastructure.opensearch import Conflict, Written


class CrawlStarter:
    def __init__(
        self,
        *,
        config: LifecycleConfig,
        results: DeletionResults,
        source_locks: SourceLocks,
        clock: Clock,
    ) -> None:
        self._config = config
        self._results = results
        self._source_locks = source_locks
        self._clock = clock

    def start(self, notification: StartNotification) -> None:
        """開始通知を受理する。拒否は `NotificationRejectedError` のサブクラス(状態は変えない)。"""
        with self._source_locks.hold(notification.source_id):
            existing = self._results.fetch_result(notification.crawl_id)
            if existing is not None:
                _check_resend(existing.record, notification)
                return
            self._advance_generation(notification)
            self._supersede_unfinished_results(notification)
            self._results.create_result(self._new_result(notification))

    def _advance_generation(self, notification: StartNotification) -> None:
        def attempt() -> bool | Conflict:
            current = self._results.fetch_generation(notification.source_id)
            if current is not None and _is_older(
                notification.crawl_started_at, current.record.crawl_started_at
            ):
                raise StaleCrawlStartedAtError
            generation = DeletionRecord(
                source_id=notification.source_id,
                crawl_id=notification.crawl_id,
                crawl_started_at=notification.crawl_started_at,
                ttl=notification.ttl,
                ratio_threshold=float(notification.ratio_threshold),
                min_delete_count=notification.min_delete_count,
                force_delete=notification.force_delete,
                updated_at=self._clock.now(),
            )
            outcome = self._results.replace_generation(current, generation)
            return True if isinstance(outcome, Written) else Conflict()

        retry_after_conflict(attempt, max_rereads=self._config.write_conflict_max_rereads)

    def _supersede_unfinished_results(self, notification: StartNotification) -> None:
        for old in self._results.list_running_without_finish(notification.source_id):
            self._supersede(old.crawl_id)

    def _supersede(self, crawl_id: str) -> None:
        def attempt() -> bool | Conflict:
            current = self._results.fetch_result(crawl_id)
            # 読み直したら、終端状態になった・終了通知を受理済みになった・消えた場合は何もしない
            # (受理済みの結果は止めない。arch 9.9 項4)。
            if current is None or current.record.status.is_terminal:
                return True
            if current.record.finish_received_at is not None:
                return True
            outcome = self._results.transition_to_terminal(
                current, DeletionStatus.DISCARDED, reason=DeletionReason.SUPERSEDED
            )
            # 409 も文書なしも読み直す(消えていれば次の確認で何もしない)。
            return True if isinstance(outcome, Written) else Conflict()

        retry_after_conflict(attempt, max_rereads=self._config.write_conflict_max_rereads)

    def _new_result(self, notification: StartNotification) -> DeletionResultRecord:
        return DeletionResultRecord(
            crawl_id=notification.crawl_id,
            source_id=notification.source_id,
            status=DeletionStatus.RUNNING,
            started_at=self._clock.now(),
            crawl_started_at=notification.crawl_started_at,
            ttl=notification.ttl,
            ratio_threshold=float(notification.ratio_threshold),
            min_delete_count=notification.min_delete_count,
            forced=notification.force_delete,
            rewrite_mode=notification.rewrite_mode,
        )


def _check_resend(existing: DeletionResultRecord, notification: StartNotification) -> None:
    """同じ `crawl_id` の結果があるとき。一致する再送なら何も返さず(成功)、それ以外は拒否する。"""
    if existing.status.is_terminal:
        raise CrawlAlreadyFinishedError
    if not _copies_match(existing, notification):
        raise CrawlStartConflictError


def _copies_match(existing: DeletionResultRecord, notification: StartNotification) -> bool:
    """複写済みの 7 項目と、正規化後の値で完全一致するか(K24、K33、K37)。

    `crawl_started_at` はミリ秒精度の UTC に揃えて比べる(表記の違いでは 409 にしない)。
    """
    return (
        existing.source_id == notification.source_id
        and format_instant(existing.crawl_started_at)
        == format_instant(notification.crawl_started_at)
        and existing.ttl == notification.ttl
        and existing.ratio_threshold == notification.ratio_threshold
        and existing.min_delete_count == notification.min_delete_count
        and existing.forced == notification.force_delete
        and existing.rewrite_mode == notification.rewrite_mode
    )


def _is_older(candidate: datetime, reference: datetime) -> bool:
    # 正規化した文字列は固定長の UTC 表記で、辞書順が時刻順になる(ミリ秒未満は比べない)。
    return format_instant(candidate) < format_instant(reference)
