"""削除の入口(ファサード。module 4.2 の「公開する入口」のうち、削除の側)。

削除ワーカー(`start()`・`stop()`・`wake()`)と、ソース削除 1〜3 をまとめる。
`CrawlRuns`(開始・終了通知、Status、起動時整理)とは別のオブジェクトで、`main.py` が両方を作る。
2 つは起床用の `threading.Event` だけでつながる(互いに依存しない):

    wake_event = threading.Event()
    runs = CrawlRuns(config=..., deletions_store=..., clock=..., wake=wake_event.set)
    deletion = create_deletion_manager(..., results=runs.results, wake_event=wake_event)

削除用のソース単位の排他(`SourceBatchExclusion`)は、ここで専用のインスタンスを作る
(`CrawlRuns` の開始・終了通知の直列化とも、`documents` の登録のロックとも別。案 19)。
"""

import threading
from collections.abc import Callable

from loreley_indexer.common.clock import Clock
from loreley_indexer.common.locks import LockInfo
from loreley_indexer.crawl_runs.deletion.config import DeletionConfig
from loreley_indexer.crawl_runs.deletion.exclusion import SourceBatchExclusion
from loreley_indexer.crawl_runs.deletion.executor import BatchExecutor, Jitter, default_jitter
from loreley_indexer.crawl_runs.deletion.judge import DeletionJudge
from loreley_indexer.crawl_runs.deletion.processor import DeletionProcessor
from loreley_indexer.crawl_runs.deletion.result_writer import ResultWriter
from loreley_indexer.crawl_runs.deletion.source_deletion import SourceDeletion
from loreley_indexer.crawl_runs.deletion.targets import TargetCollector
from loreley_indexer.crawl_runs.deletion.worker import DeletionWorker
from loreley_indexer.crawl_runs.lifecycle import DeletionResults
from loreley_indexer.infrastructure.opensearch import JobsReader, SearchIndexRepository


class DeletionManager:
    """削除ワーカーとソース削除の入口。

    `worker`(`run_once()`)と `processor`(`process(crawl_id)`)は、スレッドを起動せずに進める
    テストのために公開する。
    """

    def __init__(
        self,
        *,
        worker: DeletionWorker,
        processor: DeletionProcessor,
        source_deletion: SourceDeletion,
    ) -> None:
        self.worker = worker
        self.processor = processor
        self._source_deletion = source_deletion

    def start(self) -> None:
        """削除ワーカーを起動する。起動時の整理(`fail_unfinished_crawls_after_restart`)の後に呼ぶ。"""
        self.worker.start()

    def stop(self) -> None:
        self.worker.stop()

    def wake(self) -> None:
        self.worker.wake()

    def discard_source_crawls(self, source_id: str, lock: LockInfo) -> list[str]:
        """ソース削除 1(`POST /sources/{source_id}/deletions:discard`)。破棄した結果の ID。"""
        return self._source_deletion.discard_source_crawls(source_id, lock)

    def delete_source_documents(self, source_id: str, lock: LockInfo) -> int:
        """ソース削除 2(`DELETE /sources/{source_id}/documents`)。削除した件数。"""
        return self._source_deletion.delete_source_documents(source_id, lock)

    def delete_source_records(self, source_id: str, lock: LockInfo) -> bool:
        """ソース削除 3(`DELETE /sources/{source_id}/deletion-records`)。消したら True。"""
        return self._source_deletion.delete_source_records(source_id, lock)


def create_deletion_manager(
    config: DeletionConfig,
    *,
    results: DeletionResults,
    search_index: SearchIndexRepository,
    jobs: JobsReader,
    clock: Clock,
    wake_event: threading.Event | None = None,
    jitter: Jitter = default_jitter,
    sleep: Callable[[float], object] | None = None,
) -> DeletionManager:
    """`sleep` を省略すると、停止の要請で中断できる待ち(`stop_event.wait`)になる(本番の配線)。"""
    stop_event = threading.Event()
    wake_event = wake_event if wake_event is not None else threading.Event()
    exclusion = SourceBatchExclusion()
    writer = ResultWriter(results, max_rereads=config.write_conflict_max_rereads)
    executor = BatchExecutor(
        config=config,
        search_index=search_index,
        jobs=jobs,
        clock=clock,
        exclusion=exclusion,
        writer=writer,
        sleep=sleep if sleep is not None else stop_event.wait,
        jitter=jitter,
        should_stop=stop_event.is_set,
    )
    judge = DeletionJudge(
        search_index=search_index,
        clock=clock,
        collector=TargetCollector(
            search_index,
            page_size=config.search_after_page_size,
            max_targets=config.max_deletion_targets,
        ),
    )
    processor = DeletionProcessor(
        results=results, jobs=jobs, clock=clock, writer=writer, judge=judge, executor=executor
    )
    worker = DeletionWorker(
        poll_interval_seconds=config.poll_interval_seconds,
        poll_backoff_max_seconds=config.poll_backoff_max_seconds,
        results=results,
        processor=processor,
        wake_event=wake_event,
        stop_event=stop_event,
    )
    source_deletion = SourceDeletion(
        config=config,
        results=results,
        search_index=search_index,
        jobs=jobs,
        clock=clock,
        exclusion=exclusion,
    )
    return DeletionManager(worker=worker, processor=processor, source_deletion=source_deletion)
