"""`crawl_runs` の入口(ファサード)。api 層はここだけを使う(module 4.2)。

lifecycle(開始・終了通知、Status、起動時整理)の入口。deletion(削除ワーカー・ソース削除)の入口は
別オブジェクト `DeletionManager`(`crawl_runs.deletion`)で、`main.py` が両方を作る。削除結果の
読み書きの窓口 `results` は、deletion が同じインスタンスを使う(状態更新の責務を lifecycle に
集める。R5)。

開始・終了通知の直列化に使う `SourceLocks` は、ここで専用のインスタンスを作る
(`documents` の登録・`last-seen` のロックとは別。案 19)。

`wake` は、終了通知(`enumeration_completed`)を受理して永続化したあとに呼ぶコールバックで、
削除ワーカーを起こす(待機中を進める契機。案 2)。`main.py` が先に起床用のイベントを作り、
`wake=event.set` をここへ、同じイベントを削除ワーカーへ渡す(互いに依存しない)。
"""

from collections.abc import Callable

from loreley_indexer.common.clock import Clock
from loreley_indexer.common.source_locks import SourceLocks
from loreley_indexer.crawl_runs.lifecycle import (
    CrawlStarter,
    CrawlStatus,
    DeletionResults,
    FinishNotification,
    FinishReceiver,
    LifecycleConfig,
    RestartCleaner,
    StartNotification,
    StatusReader,
)
from loreley_indexer.infrastructure.opensearch import StoreRepository


class CrawlRuns:
    def __init__(
        self,
        *,
        config: LifecycleConfig,
        deletions_store: StoreRepository,
        clock: Clock,
        wake: Callable[[], None],
    ) -> None:
        self.results = DeletionResults(
            deletions_store, retention_count=config.deletion_retention_count, clock=clock
        )
        source_locks = SourceLocks()
        self._starter = CrawlStarter(
            config=config, results=self.results, source_locks=source_locks, clock=clock
        )
        self._finish_receiver = FinishReceiver(
            config=config,
            results=self.results,
            source_locks=source_locks,
            clock=clock,
            wake=wake,
        )
        self._status_reader = StatusReader(self.results)
        self._restart_cleaner = RestartCleaner(config=config, results=self.results)

    def start_crawl(self, notification: StartNotification) -> None:
        """開始通知(`POST /crawls/start`)。成功は `crawl_id` と `status=running` の応答。"""
        self._starter.start(notification)

    def finish_crawl(self, notification: FinishNotification) -> None:
        """終了通知(`POST /crawls/{crawl_id}/finish`)。正常終了が 202。"""
        self._finish_receiver.accept(notification)

    def crawl_status(self, crawl_id: str) -> CrawlStatus:
        """Status API(`GET /crawls/{crawl_id}`)。結果がなければ `CrawlNotFoundError`(404)。"""
        return self._status_reader.read(crawl_id)

    def fail_unfinished_crawls_after_restart(self) -> int:
        """起動時の整理。`main.py` が HTTP の受け付け前に 1 回呼ぶ。`failed` にした件数を返す。"""
        return self._restart_cleaner.fail_unfinished_results()
