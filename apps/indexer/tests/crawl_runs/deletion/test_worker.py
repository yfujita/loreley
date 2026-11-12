"""削除ワーカー(案 2: 走査型+起床通知)。

`run_once()` を直接呼び、スリープ・実スレッドに頼らずに決定的に確認する。
実スレッドを使うのは、起動・起床・停止の 2 件だけ。
"""

import logging
import threading
import time
from dataclasses import replace

import pytest

from loreley_indexer.crawl_runs import (
    CrawlRuns,
    DeletionConfig,
    DeletionManager,
    DeletionOutcome,
    create_deletion_manager,
)
from loreley_indexer.crawl_runs.deletion.worker import DeletionWorker
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionResults,
    DeletionStatus,
    deletion_result_record_id,
)
from loreley_indexer.infrastructure.opensearch import OpenSearchUnavailableError, StoreJobsReader
from tests.crawl_runs.deletion.scenario import (
    EXPIRED_AT,
    SEEN_AT,
    SEEN_BASE,
    ids,
    queued_result,
    received_at,
    seed_documents,
)
from tests.crawl_runs.factories import (
    CRAWL_ID,
    MALFORMED_VALUE,
    make_finish,
    make_start,
    seed_malformed_result,
    seed_result,
    stored_result,
)
from tests.fakes import in_memory_search_index as index_ops
from tests.fakes import in_memory_store as store_ops
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore
from tests.fakes.waiting import wait_until

SENTINEL = "sentinel-document-body"


# --- run_once ---


def test_run_once_does_nothing_when_nothing_is_queued(
    manager: DeletionManager, deletions_store: InMemoryStore
) -> None:
    assert manager.worker.run_once() is False
    assert deletions_store.write_calls() == []


def test_run_once_processes_the_oldest_receipt_first_across_sources(  # 案 2(全ソース直列)
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    seed_documents(search_index, ids(SEEN_BASE, 2), last_seen_at=SEEN_AT)
    seed_documents(search_index, ids(7_000, 2), last_seen_at=SEEN_AT, source_id="s2")
    seed_result(
        deletions_store,
        queued_result(
            "job-s2", enumerated_count=2, source_id="s2", finish_received_at=received_at(1)
        ),
    )
    seed_result(deletions_store, queued_result("job-s1", enumerated_count=2))

    assert manager.worker.run_once() is True
    assert stored_result(deletions_store, "job-s1").status is DeletionStatus.DELETED
    assert stored_result(deletions_store, "job-s2").status is DeletionStatus.RUNNING

    assert manager.worker.run_once() is True
    assert stored_result(deletions_store, "job-s2").status is DeletionStatus.DELETED

    assert manager.worker.run_once() is False


def test_results_that_are_not_queued_are_never_processed(
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    """終了通知が届いていない結果や、終端状態の結果は、待ち行列にない。"""
    seed_result(
        deletions_store, queued_result("job-a", enumerated_count=0, finish_received_at=None)
    )
    seed_result(
        deletions_store,
        queued_result("job-b", enumerated_count=0, status=DeletionStatus.DISCARDED),
    )

    assert manager.worker.run_once() is False
    assert deletions_store.write_calls() == []


def test_a_malformed_record_does_not_stop_the_queue_scan_and_the_others_are_processed(  # A6
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    caplog: pytest.LogCaptureFixture,
) -> None:
    seed_documents(search_index, ids(SEEN_BASE, 2), last_seen_at=SEEN_AT)
    bad_record_id = seed_malformed_result(
        deletions_store,
        crawl_id="job-bad",
        finish_received_at=received_at(0),
        finish_request_digest="d" * 64,
    )
    bad_body = deletions_store.body_of(bad_record_id)
    seed_result(
        deletions_store,
        queued_result(
            "job-good", enumerated_count=2, source_id="s2", finish_received_at=received_at(1)
        ),
    )
    seed_documents(search_index, ids(7_000, 2), last_seen_at=SEEN_AT, source_id="s2")

    with caplog.at_level(logging.WARNING):
        assert manager.worker.run_once() is True

    assert stored_result(deletions_store, "job-good").status is DeletionStatus.DELETED
    assert deletions_store.body_of(bad_record_id) == bad_body  # 不正な記録は書き換えない
    assert bad_record_id in caplog.text
    assert MALFORMED_VALUE not in caplog.text


class StubProcessor:
    def __init__(self, outcome: DeletionOutcome | Exception) -> None:
        self.outcome = outcome  # テストの途中で差し替えられる
        self.processed: list[str] = []

    def process(self, crawl_id: str) -> DeletionOutcome:
        self.processed.append(crawl_id)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def make_worker(
    results: DeletionResults, processor: StubProcessor, **overrides: object
) -> DeletionWorker:
    arguments = {
        "poll_interval_seconds": 30.0,
        "poll_backoff_max_seconds": 240.0,
        "results": results,
        "processor": processor,
        "wake_event": threading.Event(),
        "stop_event": threading.Event(),
    }
    return DeletionWorker(**{**arguments, **overrides})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("outcome", "continues"),
    [
        (DeletionOutcome.FINISHED, True),
        (DeletionOutcome.CLOSED, True),  # 結果が消えた・終端になった: 待ち行列に残りがありうる
        (DeletionOutcome.WAITING, False),  # 待機: すぐに再走査しても進まない
        (DeletionOutcome.NOT_QUEUED, False),
        (DeletionOutcome.STOPPED, False),
    ],
)
def test_run_once_tells_whether_to_scan_again_immediately(
    results: DeletionResults,
    deletions_store: InMemoryStore,
    outcome: DeletionOutcome,
    continues: bool,
) -> None:
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    processor = StubProcessor(outcome)

    assert make_worker(results, processor).run_once() is continues
    assert processor.processed == ["job-a"]


def test_a_failure_in_processing_does_not_stop_the_worker_and_logs_only_the_id_and_the_class(
    results: DeletionResults,
    deletions_store: InMemoryStore,
    caplog: pytest.LogCaptureFixture,
) -> None:
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    worker = make_worker(results, StubProcessor(RuntimeError(f"failed on {SENTINEL}")))

    with caplog.at_level(logging.WARNING):
        assert worker.run_once() is False

    assert "job-a" in caplog.text
    assert "RuntimeError" in caplog.text
    assert SENTINEL not in caplog.text  # 本文・値は出さない(R9)
    assert not any(record.exc_info for record in caplog.records)  # トレースバックも付けない


def test_a_failure_in_scanning_the_queue_is_logged_by_class_name_only(
    results: DeletionResults,
    deletions_store: InMemoryStore,
    caplog: pytest.LogCaptureFixture,
) -> None:
    deletions_store.behavior.inject(
        store_ops.LIST, OpenSearchUnavailableError(f"http_503 {SENTINEL}"), times=1
    )

    with caplog.at_level(logging.WARNING):
        assert make_worker(results, StubProcessor(DeletionOutcome.FINISHED)).run_once() is False

    assert "OpenSearchUnavailableError" in caplog.text
    assert SENTINEL not in caplog.text


def test_after_a_failure_the_next_scan_processes_the_same_result_again(
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    seed_documents(search_index, ids(SEEN_BASE, 2), last_seen_at=SEEN_AT)
    seed_result(deletions_store, queued_result("job-a", enumerated_count=2))
    search_index.behavior.inject(index_ops.REFRESH, OpenSearchUnavailableError("http_503"), times=1)

    assert manager.worker.run_once() is False
    assert stored_result(deletions_store, "job-a").status is DeletionStatus.RUNNING

    assert manager.worker.run_once() is True
    assert stored_result(deletions_store, "job-a").status is DeletionStatus.DELETED


# --- 連続失敗のバックオフ(A1) ---

POLL = 2.0
BACKOFF_MAX = 20.0


def make_backoff_worker(
    results: DeletionResults, processor: StubProcessor, **overrides: object
) -> DeletionWorker:
    return make_worker(
        results,
        processor,
        poll_interval_seconds=POLL,
        poll_backoff_max_seconds=BACKOFF_MAX,
        **overrides,
    )


def fail_n_times(worker: DeletionWorker, times: int) -> None:
    for _ in range(times):
        assert worker.run_once() is False


def test_the_wait_doubles_with_each_consecutive_failure_up_to_the_maximum(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    worker = make_backoff_worker(results, StubProcessor(RuntimeError("boom")))
    assert worker.next_wait_seconds() == POLL

    waits = []
    for _ in range(6):
        fail_n_times(worker, 1)
        waits.append(worker.next_wait_seconds())

    assert waits == [4.0, 8.0, 16.0, BACKOFF_MAX, BACKOFF_MAX, BACKOFF_MAX]


def test_the_wait_stays_at_the_maximum_however_long_the_failures_continue(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    worker = make_backoff_worker(results, StubProcessor(RuntimeError("boom")))

    fail_n_times(worker, 2_000)  # 倍々の計算が溢れない

    assert worker.next_wait_seconds() == BACKOFF_MAX


def test_the_maximum_equal_to_the_poll_interval_never_lengthens_the_wait(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    worker = make_worker(
        results,
        StubProcessor(RuntimeError("boom")),
        poll_interval_seconds=POLL,
        poll_backoff_max_seconds=POLL,
    )

    fail_n_times(worker, 3)

    assert worker.next_wait_seconds() == POLL


@pytest.mark.parametrize(
    "recovery",
    [DeletionOutcome.FINISHED, DeletionOutcome.WAITING, "empty_queue"],
)
def test_a_run_without_a_failure_resets_the_wait(
    results: DeletionResults, deletions_store: InMemoryStore, recovery: DeletionOutcome | str
) -> None:
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    processor = StubProcessor(RuntimeError("boom"))
    worker = make_backoff_worker(results, processor)
    fail_n_times(worker, 3)
    assert worker.next_wait_seconds() > POLL

    if isinstance(recovery, DeletionOutcome):
        processor.outcome = recovery
    else:
        deletions_store.delete(deletion_result_record_id("job-a"))
    worker.run_once()

    assert worker.next_wait_seconds() == POLL


def test_the_recovery_is_logged_once_with_only_the_failure_count(
    results: DeletionResults, deletions_store: InMemoryStore, caplog: pytest.LogCaptureFixture
) -> None:
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    processor = StubProcessor(RuntimeError(SENTINEL))
    worker = make_backoff_worker(results, processor)
    fail_n_times(worker, 3)
    processor.outcome = DeletionOutcome.FINISHED
    caplog.clear()

    with caplog.at_level(logging.DEBUG):
        worker.run_once()
        worker.run_once()  # 失敗が続いていないときは出さない

    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert [r.getMessage() for r in infos] == [
        "deletion worker recovered after 3 consecutive failures"
    ]
    assert "job-a" not in caplog.text
    assert SENTINEL not in caplog.text


def test_failures_after_a_recovery_are_counted_from_one_again(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    processor = StubProcessor(RuntimeError("boom"))
    worker = make_backoff_worker(results, processor)
    fail_n_times(worker, 3)
    processor.outcome = DeletionOutcome.FINISHED
    worker.run_once()
    processor.outcome = RuntimeError("boom")

    fail_n_times(worker, 1)

    assert worker.next_wait_seconds() == 2 * POLL


def test_a_failure_in_scanning_the_queue_lengthens_the_wait_too(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    deletions_store.behavior.inject(store_ops.LIST, OpenSearchUnavailableError("http_503"), times=2)
    worker = make_backoff_worker(results, StubProcessor(DeletionOutcome.FINISHED))

    fail_n_times(worker, 2)

    assert worker.next_wait_seconds() == 4 * POLL


def test_a_failure_that_follows_a_successful_scan_is_still_counted(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    """走査が成功しても、処理が失敗していれば失敗が続いている(走査の成功で数えを戻さない)。"""
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    worker = make_backoff_worker(results, StubProcessor(RuntimeError("boom")))

    fail_n_times(worker, 3)

    assert worker.next_wait_seconds() == 8 * POLL


def test_the_thread_waits_longer_after_each_failure_and_a_wake_does_not_reset_the_count(
    results: DeletionResults,
    deletions_store: InMemoryStore,
) -> None:
    """起床通知では間隔の途中でも再試行するが、連続失敗の回数は保つ。待ちは実際には行わない。"""
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    wake_event = threading.Event()
    stop_event = threading.Event()
    waits: list[float] = []
    wake_was_set: list[bool] = []

    def record_the_wait(seconds: float) -> bool:
        waits.append(seconds)
        wake_was_set.append(wake_event.is_set())
        if len(waits) == 5:
            stop_event.set()
        return len(waits) == 3  # 3 回目の待ちは、起床通知で戻る

    worker = make_backoff_worker(
        results,
        StubProcessor(RuntimeError("boom")),
        wake_event=wake_event,
        stop_event=stop_event,
        wait=record_the_wait,
    )
    wake_event.set()  # 3 回目の待ちで受け取った通知
    worker.start()
    assert wait_until(stop_event.is_set)
    worker.stop()

    assert waits == [4.0, 8.0, 16.0, BACKOFF_MAX, BACKOFF_MAX]
    assert wake_was_set == [True, True, True, False, False]  # 通知で戻ったら、通知を消す


def test_repeated_failures_log_a_warning_only_at_powers_of_two_and_never_log_values(
    results: DeletionResults,
    deletions_store: InMemoryStore,
    caplog: pytest.LogCaptureFixture,
) -> None:
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    processor = StubProcessor(RuntimeError(f"failed on {SENTINEL}"))
    worker = make_backoff_worker(results, processor)

    with caplog.at_level(logging.DEBUG):
        fail_n_times(worker, 9)
        processor.outcome = DeletionOutcome.FINISHED
        worker.run_once()
        processor.outcome = RuntimeError(f"failed on {SENTINEL}")
        fail_n_times(worker, 1)  # 成功のあとの失敗は、また 1 回目として警告する

    warnings = [
        record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING
    ]
    assert [message.rsplit("=", 1)[1] for message in warnings] == ["1", "2", "4", "8", "1"]
    assert all("job-a" in message and "RuntimeError" in message for message in warnings)
    assert SENTINEL not in caplog.text  # デバッグを含め、値は出さない(R9)
    assert not any(record.exc_info for record in caplog.records)


# --- 起床通知 ---


def test_accepting_a_finish_notification_wakes_the_worker_through_the_shared_event(
    crawl_runs: CrawlRuns, manager: DeletionManager, wake_event: threading.Event
) -> None:
    crawl_runs.start_crawl(make_start())
    assert not wake_event.is_set()

    crawl_runs.finish_crawl(make_finish(skipped_document_ids=(), enumerated_count=0))

    assert wake_event.is_set()


def test_the_manager_wake_sets_the_event(
    manager: DeletionManager, wake_event: threading.Event
) -> None:
    manager.wake()

    assert wake_event.is_set()


# --- 実スレッド(起動・起床・停止) ---


def test_the_started_worker_processes_a_result_when_woken_without_waiting_for_the_poll(
    crawl_runs: CrawlRuns,
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
) -> None:
    """走査の間隔は 30 秒。起床通知で、待たずに処理される(案 2)。"""
    seed_documents(search_index, ids(SEEN_BASE, 2), last_seen_at=SEEN_AT)
    seed_documents(search_index, ids(2_000, 2), last_seen_at=EXPIRED_AT)
    crawl_runs.start_crawl(make_start(ttl=3 * 86_400))
    manager.start()
    try:
        crawl_runs.finish_crawl(
            make_finish(enumerated_count=2, skipped_document_ids=(), oversize_document_ids=())
        )

        assert wait_until(
            lambda: stored_result(deletions_store, CRAWL_ID).status is DeletionStatus.DELETED
        )
    finally:
        manager.stop()


def test_stop_ends_the_thread_even_while_it_waits_for_the_next_poll(
    manager: DeletionManager,
) -> None:
    manager.start()
    thread = (
        manager.worker._thread
    )  # 他のテストのスレッドと取り違えないよう、自分のスレッドで確認する
    assert thread is not None
    assert thread.is_alive()

    manager.stop()

    assert not thread.is_alive()
    with pytest.raises(RuntimeError):
        manager.start()  # 起動は 1 回だけ。`stop()` のあとの再起動はできない


# --- 本番の配線(`create_deletion_manager` の既定。S3) ---


def make_production_wired_manager(
    results: DeletionResults,
    search_index: InMemorySearchIndex,
    jobs_reader: StoreJobsReader,
    clock: FixedClock,
    deletion_config: DeletionConfig,
    **overrides: float,
) -> DeletionManager:
    """`sleep`・`jitter`・`wake_event` を渡さない(本番と同じ既定の配線)。"""
    return create_deletion_manager(
        replace(deletion_config, **overrides),
        results=results,
        search_index=search_index,
        jobs=jobs_reader,
        clock=clock,
    )


def test_the_production_wiring_uses_the_configured_poll_interval_and_backoff_maximum(
    deletion_config: DeletionConfig,
    results: DeletionResults,
    search_index: InMemorySearchIndex,
    jobs_reader: StoreJobsReader,
    clock: FixedClock,
    deletions_store: InMemoryStore,
) -> None:
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    search_index.behavior.inject(
        index_ops.REFRESH, OpenSearchUnavailableError("http_503"), times=None
    )
    production = make_production_wired_manager(
        results,
        search_index,
        jobs_reader,
        clock,
        deletion_config,
        poll_interval_seconds=3.0,
        poll_backoff_max_seconds=20.0,
    )
    assert production.worker.next_wait_seconds() == 3.0

    waits = []
    for _ in range(5):
        assert production.worker.run_once() is False
        waits.append(production.worker.next_wait_seconds())

    assert waits == [6.0, 12.0, 20.0, 20.0, 20.0]  # 設定の上限で頭打ち


def test_the_production_wiring_stops_a_thread_that_is_in_a_long_retry_wait_immediately(
    deletion_config: DeletionConfig,
    results: DeletionResults,
    search_index: InMemorySearchIndex,
    jobs_reader: StoreJobsReader,
    clock: FixedClock,
    deletions_store: InMemoryStore,
) -> None:
    """再試行の待ち(`retry_backoff_initial_seconds=30`)は、`stop()` で中断される。

    既定の `sleep` が `time.sleep` なら、停止が 30 秒待たされて 5 秒の待ちでは終わらない。
    """
    seed_documents(search_index, ids(SEEN_BASE, 1), last_seen_at=SEEN_AT)
    seed_documents(search_index, ids(2_000, 2), last_seen_at=EXPIRED_AT)
    seed_result(deletions_store, queued_result("job-a", enumerated_count=1))
    # 削除が失敗し続ける(全体異常)。1 回目の失敗のあと、30 秒の再試行の待ちに入る。
    search_index.behavior.inject(
        index_ops.FETCH_FOR_DELETION, OpenSearchUnavailableError("http_503"), times=None
    )
    production = make_production_wired_manager(
        results,
        search_index,
        jobs_reader,
        clock,
        deletion_config,
        retry_backoff_initial_seconds=30.0,
        retry_backoff_max_seconds=30.0,
    )
    production.start()
    try:
        assert wait_until(
            lambda: len(search_index.behavior.calls_of(index_ops.FETCH_FOR_DELETION)) >= 1
        )  # 再試行の待ちに入った

        started = time.monotonic()
        production.stop()

        elapsed_seconds = time.monotonic() - started
    finally:
        production.stop()

    assert elapsed_seconds < 5.0
    assert production.worker._thread is not None
    assert not production.worker._thread.is_alive()
    # 中断された削除は結果を変えない(次回起動の整理で `indexer_restart` になる)。
    assert stored_result(deletions_store, "job-a").status is DeletionStatus.RUNNING
