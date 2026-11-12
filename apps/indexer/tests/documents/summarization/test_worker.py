"""要約ワーカーと、`documents` が公開する入口(`Summarization`)。

`run_once()` を直接呼び、スリープにも実スレッドにも頼らずに決定的に確認する。
スレッドを使うのは、起動・停止の動作を確認する 1 件だけ。
"""

import logging
import threading
import time
from dataclasses import replace

import pytest

from loreley_indexer.documents.summarization import (
    SubmitResult,
    Summarization,
    SummarizationConfig,
    SummaryRequestQueue,
    SummaryRescanner,
    SummaryWorkerPool,
    create_summarization,
)
from loreley_indexer.documents.summarization.worker import IDLE_WAIT_SECONDS
from loreley_indexer.infrastructure.llm import LlmFailure, LlmFailureKind
from loreley_indexer.infrastructure.opensearch import OpenSearchUnavailableError, StoreJobsReader
from tests.documents.factories import set_maintenance, source_of, status_of
from tests.documents.summarization.conftest import (
    MAX_ATTEMPTS,
    MIN_RESCAN_INTERVAL_SECONDS,
    seed_pending,
    signal_when_a_taker_waits,
)
from tests.fakes import in_memory_search_index as ops
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore
from tests.fakes.llm import FakeLlmClient


def test_run_once_processes_one_request(
    pool: SummaryWorkerPool,
    summary_requests: SummaryRequestQueue,
    search_index: InMemorySearchIndex,
) -> None:
    seed_pending(search_index, "a")
    seed_pending(search_index, "b")
    summary_requests.submit("a")
    summary_requests.submit("b")

    assert pool.run_once() is True

    assert status_of(search_index, "a") == "generated"
    assert status_of(search_index, "b") == "pending"


def test_idle_run_once_does_nothing(pool: SummaryWorkerPool, llm: FakeLlmClient) -> None:
    assert pool.run_once() is False
    assert llm.prompts == []


def test_run_once_does_not_wait_when_a_request_is_already_queued(
    pool: SummaryWorkerPool,
    summary_requests: SummaryRequestQueue,
    search_index: InMemorySearchIndex,
) -> None:
    seed_pending(search_index, "a")
    summary_requests.submit("a")
    started_at = time.monotonic()

    assert pool.run_once(wait_seconds=30.0) is True

    assert time.monotonic() - started_at < 5.0


def test_idle_run_once_does_not_wait_unless_asked(pool: SummaryWorkerPool) -> None:
    started_at = time.monotonic()

    assert pool.run_once() is False

    assert time.monotonic() - started_at < 1.0


def test_idle_run_once_waits_for_the_asked_time_and_returns_false(
    pool: SummaryWorkerPool,
) -> None:
    started_at = time.monotonic()

    assert pool.run_once(wait_seconds=0.2) is False

    assert time.monotonic() - started_at >= 0.15


def test_run_once_picks_up_a_request_submitted_by_another_thread_while_waiting(
    pool: SummaryWorkerPool,
    summary_requests: SummaryRequestQueue,
    search_index: InMemorySearchIndex,
) -> None:
    seed_pending(search_index, "a")
    submitter = threading.Thread(target=lambda: summary_requests.submit("a"), daemon=True)
    submitter.start()

    assert pool.run_once(wait_seconds=5.0) is True

    submitter.join(5.0)
    assert status_of(search_index, "a") == "generated"


def test_waiting_run_once_is_woken_by_a_submit_after_it_started_waiting(
    pool: SummaryWorkerPool,
    summary_requests: SummaryRequestQueue,
    search_index: InMemorySearchIndex,
) -> None:
    """待ちに入ってから依頼が積まれると、待ち時間を使い切らずに処理する(`submit` の `notify()`)。"""
    seed_pending(search_index, "a")
    waiting = signal_when_a_taker_waits(summary_requests)
    processed: list[bool] = []
    started_at = time.monotonic()
    thread = threading.Thread(
        target=lambda: processed.append(pool.run_once(wait_seconds=30.0)), daemon=True
    )
    thread.start()
    assert waiting.wait(5.0)

    summary_requests.submit("a")
    thread.join(5.0)

    assert not thread.is_alive()
    assert processed == [True]
    assert time.monotonic() - started_at < 5.0
    assert status_of(search_index, "a") == "generated"


def test_registration_to_summary_end_to_end_without_threads(
    pool: SummaryWorkerPool,
    summary_requests: SummaryRequestQueue,
    search_index: InMemorySearchIndex,
) -> None:
    """登録の成功後に依頼が積まれ、ワーカーが生成して書き戻す(M-9)。"""
    seed_pending(search_index, "a")
    summary_requests.submit("a")

    pool.run_once()

    stored = source_of(search_index, "a")
    assert stored["summary_status"] == "generated"
    assert stored["summary"].startswith("summary")


def test_llm_failure_is_isolated_and_requests_a_rescan(
    pool: SummaryWorkerPool,
    summary_requests: SummaryRequestQueue,
    search_index: InMemorySearchIndex,
    llm: FakeLlmClient,
    rescanner: SummaryRescanner,
) -> None:
    """LLM の失敗は例外にならず、`pending` のまま残って再走査の対象になる(案12)。"""
    seed_pending(search_index, "a")
    summary_requests.submit("a")
    for _ in range(MAX_ATTEMPTS):
        llm.queue_result(LlmFailure(LlmFailureKind.TIMEOUT))

    assert pool.run_once() is True

    assert status_of(search_index, "a") == "pending"
    assert rescanner.run_if_due() == 1  # 要請が出ている(初回なので間隔の下限に当たらない)


def test_unexpected_processing_error_does_not_stop_the_other_requests(
    pool: SummaryWorkerPool,
    summary_requests: SummaryRequestQueue,
    search_index: InMemorySearchIndex,
    rescanner: SummaryRescanner,
) -> None:
    """OpenSearch の全体異常などは、そのワーカーを落とさず、ほかの依頼を処理する。"""
    seed_pending(search_index, "a")
    seed_pending(search_index, "b")
    summary_requests.submit("a")
    summary_requests.submit("b")
    search_index.behavior.inject(ops.FETCH, OpenSearchUnavailableError("http_503"), key="a")

    assert pool.run_once() is True  # a: 失敗
    assert pool.run_once() is True  # b: 成功
    search_index.refresh()  # 検索は refresh 後の状態を見る

    assert status_of(search_index, "a") == "pending"
    assert status_of(search_index, "b") == "generated"
    assert rescanner.run_if_due() == 1  # a だけが再走査の対象になる


def test_failed_rescan_does_not_break_the_step_and_is_requested_again(
    pool: SummaryWorkerPool,
    rescanner: SummaryRescanner,
    search_index: InMemorySearchIndex,
    clock: FixedClock,
) -> None:
    """再走査の失敗(OpenSearch の全体異常)でステップを落とさず、次の機会に再走査する。"""
    seed_pending(search_index, "a")
    rescanner.request()
    search_index.behavior.inject(ops.SEARCH_IDS, OpenSearchUnavailableError("http_503"))

    assert pool.run_once() is False  # 例外が出ない

    clock.advance(seconds=MIN_RESCAN_INTERVAL_SECONDS)
    assert pool.run_once() is True  # 再要請されていて、再走査された依頼を処理する
    assert status_of(search_index, "a") == "generated"


def test_a_written_summary_requests_no_rescan(
    pool: SummaryWorkerPool,
    summary_requests: SummaryRequestQueue,
    search_index: InMemorySearchIndex,
    rescanner: SummaryRescanner,
    clock: FixedClock,
) -> None:
    """書き戻しに成功したら、再走査は要請しない(要請し続けると、常に再走査が走る)。"""
    seed_pending(search_index, "a")
    summary_requests.submit("a")
    assert pool.run_once() is True
    search_index.refresh()
    seed_pending(search_index, "b")  # 再走査されれば拾われる `pending`

    clock.advance(seconds=MIN_RESCAN_INTERVAL_SECONDS)

    assert rescanner.run_if_due() == 0


def test_repeated_failures_make_the_rescans_rarer_and_a_written_summary_restores_them(
    pool: SummaryWorkerPool,
    rescanner: SummaryRescanner,
    search_index: InMemorySearchIndex,
    llm: FakeLlmClient,
    clock: FixedClock,
) -> None:
    """K54(3): 失敗し続ける間、LLM を叩く頻度が時間とともに下がる。1 件書けたら元に戻る。"""
    seed_pending(search_index, "a")
    for _ in range(MAX_ATTEMPTS * 3):
        llm.queue_result(LlmFailure(LlmFailureKind.TIMEOUT))
    rescanner.request()

    assert pool.run_once() is True  # 起動時の走査(待たない)。1 回目の失敗
    clock.advance(seconds=60)
    assert pool.run_once() is True  # 下限の間隔で走査。2 回目の失敗
    clock.advance(seconds=60)
    assert pool.run_once() is False  # 次は 120 秒必要。まだ走査しない
    assert len(llm.prompts) == MAX_ATTEMPTS * 2
    clock.advance(seconds=60)
    assert pool.run_once() is True  # 3 回目の失敗。次は 240 秒必要
    assert len(llm.prompts) == MAX_ATTEMPTS * 3

    clock.advance(seconds=240)
    assert pool.run_once() is True  # LLM が回復して書き戻せた
    assert status_of(search_index, "a") == "generated"
    search_index.refresh()
    seed_pending(search_index, "b")
    rescanner.request()
    clock.advance(seconds=60)  # 書き戻せたので、間隔は下限(60 秒)に戻っている

    assert pool.run_once() is True
    assert status_of(search_index, "b") == "generated"


def test_maintenance_never_calls_the_llm_and_its_rescans_back_off(
    pool: SummaryWorkerPool,
    rescanner: SummaryRescanner,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
    llm: FakeLlmClient,
    clock: FixedClock,
) -> None:
    """メンテナンス中は、LLM を呼ばず、再走査の間隔も伸びる。解除後に書き戻される。"""
    seed_pending(search_index, "a")
    set_maintenance(jobs_store, enabled=True)
    rescanner.request()

    assert pool.run_once() is True  # 走査して依頼を処理する(止まる)
    clock.advance(seconds=60)
    assert pool.run_once() is True  # 下限の間隔で、もう 1 回(止まる)
    clock.advance(seconds=60)
    assert pool.run_once() is False  # 次は 120 秒必要
    assert llm.prompts == []

    set_maintenance(jobs_store, enabled=False)
    clock.advance(seconds=60)
    assert pool.run_once() is True

    assert status_of(search_index, "a") == "generated"
    assert len(llm.prompts) == 1


def test_stop_request_prevents_further_llm_attempts(
    config: SummarizationConfig,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
    clock: FixedClock,
) -> None:
    """停止を要請すると、生成中の処理は残りの試行(バックオフの待ちを含む)を行わずに終わる。

    本番の配線(`sleep=stop_event.wait`)の確認のため、バックオフを長くして実際に待たせる。
    配線が `time.sleep` などに退行したときだけ 30 秒かかって失敗する向きで、正常時は待たない。
    """
    long_backoff_config = replace(
        config, retry_backoff_initial_seconds=30.0, retry_backoff_max_seconds=30.0
    )
    handles: list[Summarization] = []
    llm = FakeLlmClient(on_generate=lambda _prompt: handles[0].stop())
    for _ in range(MAX_ATTEMPTS):
        llm.queue_result(LlmFailure(LlmFailureKind.TIMEOUT))
    handle = create_summarization(
        long_backoff_config,
        search_index=search_index,
        jobs=StoreJobsReader(jobs_store),
        llm=llm,
        clock=clock,
    )
    handles.append(handle)
    seed_pending(search_index, "a")
    handle.requests.submit("a")
    started_at = time.monotonic()

    assert handle.workers.run_once() is True

    assert time.monotonic() - started_at < 5.0
    assert len(llm.prompts) == 1
    assert status_of(search_index, "a") == "pending"


def test_unexpected_llm_error_is_logged_without_its_message(
    pool: SummaryWorkerPool,
    summary_requests: SummaryRequestQueue,
    search_index: InMemorySearchIndex,
    llm: FakeLlmClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """R9: 想定外の例外のメッセージ(本文を含みうる)は出さず、例外の種類と文書 ID だけ。"""
    seed_pending(search_index, "doc-for-log")
    summary_requests.submit("doc-for-log")
    llm.queue_result(RuntimeError("SECRET-SENTINEL"))

    with caplog.at_level(logging.DEBUG):
        assert pool.run_once() is True

    assert "SECRET-SENTINEL" not in caplog.text
    assert "doc-for-log" in caplog.text
    assert "RuntimeError" in caplog.text


def test_idle_worker_rescans_after_a_refused_request(
    config: SummarizationConfig,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
    llm: FakeLlmClient,
    clock: FixedClock,
) -> None:
    """キューが満杯で断った依頼は、`pending` のまま残り、キューが空いたあとの再走査で拾われる。"""
    one_slot_config = replace(config, queue_size=1)
    handle = create_summarization(
        one_slot_config,
        search_index=search_index,
        jobs=StoreJobsReader(jobs_store),
        llm=llm,
        clock=clock,
    )
    pool = handle.workers  # スレッドを使わず `run_once()` で進める。
    seed_pending(search_index, "a")
    seed_pending(search_index, "b")
    assert handle.requests.submit("a") is SubmitResult.ACCEPTED
    assert handle.requests.submit("b") is SubmitResult.FULL

    assert pool.run_once() is True  # a を処理する
    search_index.refresh()  # 検索は refresh 後の状態を見る(a は `generated`)
    assert pool.run_once() is True  # 空なので、断った記録から再走査して b を依頼し、処理する

    assert status_of(search_index, "a") == "generated"
    assert status_of(search_index, "b") == "generated"


def test_startup_rescan_picks_up_pending_documents_left_by_a_previous_run(
    config: SummarizationConfig,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
    llm: FakeLlmClient,
    clock: FixedClock,
) -> None:
    """C-24(a): 再起動後の再走査で `pending` の文書の要約が再生成され、`generated` になる。"""
    handle = create_summarization(
        config, search_index=search_index, jobs=StoreJobsReader(jobs_store), llm=llm, clock=clock
    )
    pool = handle.workers
    seed_pending(search_index, "left-over")
    handle.rescanner.request()  # `start()` が行う要請(スレッドは起動しない)

    assert pool.run_once() is True  # 依頼がないので再走査し、積まれた依頼を処理する

    assert status_of(search_index, "left-over") == "generated"


def started_worker_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name.startswith("summary-worker-")]


def test_started_workers_generate_and_stop_cleanly(
    config: SummarizationConfig,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
    clock: FixedClock,
) -> None:
    """起動すると再走査して要約を生成し、停止すると実行中の処理を終えてスレッドが終わる。"""
    generating = threading.Event()
    llm = FakeLlmClient(on_generate=lambda _prompt: generating.set())
    handle = create_summarization(
        replace(config, concurrency=2),
        search_index=search_index,
        jobs=StoreJobsReader(jobs_store),
        llm=llm,
        clock=clock,
    )
    seed_pending(search_index, "a")
    assert started_worker_threads() == []

    handle.start()
    assert len(started_worker_threads()) == 2
    assert generating.wait(5.0)
    stopping_at = time.monotonic()
    handle.stop()  # 実行中の生成と書き戻しを終えてから戻る

    # 待機中のワーカーは、停止の要請で起こされる(待機の 1 周期を待たない)。
    assert time.monotonic() - stopping_at < IDLE_WAIT_SECONDS
    assert status_of(search_index, "a") == "generated"
    assert started_worker_threads() == []


def test_disabled_summarization_starts_nothing_and_never_calls_the_llm(
    disabled_config: SummarizationConfig,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
    llm: FakeLlmClient,
    clock: FixedClock,
) -> None:
    """既定(無効)では、スレッドも作らず、LLM も呼ばない。"""
    handle = create_summarization(
        disabled_config,
        search_index=search_index,
        jobs=StoreJobsReader(jobs_store),
        llm=llm,
        clock=clock,
    )
    seed_pending(search_index, "a")

    handle.start()
    assert started_worker_threads() == []
    handle.stop()

    assert llm.prompts == []
    assert status_of(search_index, "a") == "pending"
