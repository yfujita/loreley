"""要約の生成と書き戻し(arch 5章、7.4)。ワーカー・スレッドを使わず、`process()` を直接呼ぶ。"""

import logging
import threading
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from loreley_indexer.common.errors import UnavailableError
from loreley_indexer.documents.summarization import (
    SummarizationConfig,
    SummaryOutcome,
    SummaryProcessor,
)
from loreley_indexer.infrastructure.llm import (
    DisabledLlmClient,
    LlmCompletion,
    LlmFailure,
    LlmFailureKind,
)
from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    OpenSearchUnavailableError,
    Rejected,
    StoreJobsReader,
)
from tests.documents.factories import (
    MALFORMED_MAINTENANCE_BODIES,
    set_maintenance,
    set_malformed_maintenance,
    source_of,
)
from tests.documents.summarization.conftest import (
    BODY,
    MAX_ATTEMPTS,
    MAX_REREADS,
    pending_source,
    seed_pending,
)
from tests.fakes import in_memory_search_index as ops
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore
from tests.fakes.llm import DEFAULT_MODEL, FakeLlmClient

DOCUMENT_ID = "doc-1"


def replace_count(search_index: InMemorySearchIndex) -> int:
    return len(search_index.behavior.calls_of(ops.REPLACE))


def change_during(search_index: InMemorySearchIndex, **fields: Any) -> None:
    """別の書き手が文書を更新する(`pending_source` の項目を上書きする)。"""
    search_index.seed(DOCUMENT_ID, {**source_of(search_index, DOCUMENT_ID), **fields})


# --- 正常系(C-25) ---


def test_summary_is_written_back_and_nothing_else_changes(
    processor: SummaryProcessor, search_index: InMemorySearchIndex, llm: FakeLlmClient
) -> None:
    """C-25: `summary`・`summary_model` が書かれ `generated` になる。ほかの項目は変わらない。"""
    seed_pending(search_index)
    before = source_of(search_index, DOCUMENT_ID)

    outcome = processor.process(DOCUMENT_ID)

    assert outcome is SummaryOutcome.WRITTEN
    assert source_of(search_index, DOCUMENT_ID) == {
        **before,
        "summary": "summary #1",
        "summary_status": "generated",
        "summary_model": DEFAULT_MODEL,
    }
    assert len(llm.prompts) == 1
    assert BODY in llm.prompts[0]
    assert "Title" in llm.prompts[0]


def test_the_model_name_comes_from_the_llm_result(
    processor: SummaryProcessor, search_index: InMemorySearchIndex, llm: FakeLlmClient
) -> None:
    seed_pending(search_index)
    llm.queue_result(LlmCompletion(text="a summary", model="some-model-2026"))

    processor.process(DOCUMENT_ID)

    assert source_of(search_index, DOCUMENT_ID)["summary"] == "a summary"
    assert source_of(search_index, DOCUMENT_ID)["summary_model"] == "some-model-2026"


def test_the_prompt_body_is_capped_but_the_stored_content_is_not(
    make_processor,
    config: SummarizationConfig,
    search_index: InMemorySearchIndex,
    llm: FakeLlmClient,
) -> None:
    seed_pending(search_index, content="x" * 5000)

    make_processor(replace(config, input_max_chars=100)).process(DOCUMENT_ID)

    assert "x" * 100 in llm.prompts[0]
    assert "x" * 101 not in llm.prompts[0]
    assert source_of(search_index, DOCUMENT_ID)["content"] == "x" * 5000


# --- 無効・対象外(arch 7.1、7.4) ---


def test_disabled_summary_never_calls_the_llm(
    make_processor,
    disabled_config: SummarizationConfig,
    search_index: InMemorySearchIndex,
    llm: FakeLlmClient,
) -> None:
    """既定は無効で、LLM を呼ばず、文書にも触れない(R9)。"""
    seed_pending(search_index)

    outcome = make_processor(disabled_config).process(DOCUMENT_ID)

    assert outcome is SummaryOutcome.DISABLED
    assert llm.prompts == []
    assert search_index.behavior.calls == []


def test_disabled_summary_does_not_even_touch_the_default_disabled_client(
    disabled_config: SummarizationConfig,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
) -> None:
    """既定の LLM クライアントは呼ぶと例外になる。無効なら呼ばないので例外にならない。"""
    seed_pending(search_index)
    processor = SummaryProcessor(
        config=disabled_config,
        search_index=search_index,
        jobs=StoreJobsReader(jobs_store),
        llm=DisabledLlmClient(),
    )

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.DISABLED


@pytest.mark.parametrize(
    "state",
    [
        {"summary_status": "generated", "summary": "done", "summary_model": "m"},
        {"summary_status": "disabled"},
    ],
    ids=["generated", "disabled"],
)
def test_document_that_is_not_pending_is_discarded_without_calling_the_llm(
    processor: SummaryProcessor,
    search_index: InMemorySearchIndex,
    llm: FakeLlmClient,
    state: dict[str, Any],
) -> None:
    seed_pending(search_index, **state)

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.DISCARDED
    assert llm.prompts == []
    assert search_index.write_calls() == []


def test_extract_failed_document_is_never_summarized(
    processor: SummaryProcessor, search_index: InMemorySearchIndex, llm: FakeLlmClient
) -> None:
    source = pending_source(DOCUMENT_ID, index_status="extract_failed", summary_status="disabled")
    del source["content"], source["text_hash"]
    search_index.seed(DOCUMENT_ID, source)

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.DISCARDED
    assert llm.prompts == []


def test_missing_document_is_discarded(
    processor: SummaryProcessor, search_index: InMemorySearchIndex, llm: FakeLlmClient
) -> None:
    assert processor.process("never-registered") is SummaryOutcome.DISCARDED
    assert llm.prompts == []


# --- 生成中の更新(C-1、C-15、E-45b) ---


def test_summary_for_an_old_body_is_discarded_when_content_hash_changed(
    processor: SummaryProcessor, search_index: InMemorySearchIndex, llm: FakeLlmClient
) -> None:
    """C-1: 生成中に原本が更新されたら、旧本文向けの要約は書かず、新しい文書は `pending` のまま。"""
    seed_pending(search_index)
    llm.on_generate = lambda _prompt: change_during(
        search_index, content_hash="n" * 64, content="new body"
    )

    outcome = processor.process(DOCUMENT_ID)

    assert outcome is SummaryOutcome.DISCARDED
    stored = source_of(search_index, DOCUMENT_ID)
    assert "summary" not in stored
    assert stored["summary_status"] == "pending"
    assert stored["content"] == "new body"


def test_summary_is_discarded_when_only_text_hash_changed(
    processor: SummaryProcessor, search_index: InMemorySearchIndex, llm: FakeLlmClient
) -> None:
    """C-15: `content_hash` が同じでも `text_hash` が変われば破棄する(K22)。"""
    seed_pending(search_index)
    llm.on_generate = lambda _prompt: change_during(search_index, text_hash="n" * 64)

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.DISCARDED
    assert "summary" not in source_of(search_index, DOCUMENT_ID)


def test_summary_is_discarded_when_the_document_was_deleted_during_generation(
    processor: SummaryProcessor, search_index: InMemorySearchIndex, llm: FakeLlmClient
) -> None:
    seed_pending(search_index)
    llm.on_generate = lambda _prompt: search_index.seed_removal(DOCUMENT_ID)

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.DISCARDED
    assert search_index.document_ids() == []
    assert search_index.write_calls() == []


def test_extract_failed_transition_before_the_write_back_discards_the_summary(
    processor: SummaryProcessor, search_index: InMemorySearchIndex, llm: FakeLlmClient
) -> None:
    """E-45b(a1): 生成中に `extract_failed` へ遷移したあとの書き戻しは、要約を破棄する。"""
    seed_pending(search_index)

    def transition_to_extract_failed(_prompt: str) -> None:
        source = source_of(search_index, DOCUMENT_ID)
        for removed in ("content", "text_hash"):
            del source[removed]
        search_index.seed(
            DOCUMENT_ID, {**source, "index_status": "extract_failed", "summary_status": "disabled"}
        )

    llm.on_generate = transition_to_extract_failed

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.DISCARDED
    stored = source_of(search_index, DOCUMENT_ID)
    assert "summary" not in stored
    assert stored["index_status"] == "extract_failed"


def test_extract_failed_transition_between_the_read_and_the_put_discards_the_summary(
    processor: SummaryProcessor, search_index: InMemorySearchIndex
) -> None:
    """E-45b(a2): GET と PUT の間の遷移で PUT が 409 になり、読み直した結果も破棄になる。"""
    seed_pending(search_index)

    def transition_to_extract_failed() -> None:
        source = source_of(search_index, DOCUMENT_ID)
        for removed in ("content", "text_hash"):
            del source[removed]
        search_index.seed(
            DOCUMENT_ID, {**source, "index_status": "extract_failed", "summary_status": "disabled"}
        )

    search_index.behavior.before(ops.REPLACE, transition_to_extract_failed)

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.DISCARDED
    assert "summary" not in source_of(search_index, DOCUMENT_ID)
    assert replace_count(search_index) == 1  # 409 になった 1 回だけ。読み直しでは PUT しない。


# --- 409 の読み直し(C-19、C-20) ---


def test_write_back_rereads_after_a_conflict_and_keeps_the_newer_last_seen_at(
    processor: SummaryProcessor, search_index: InMemorySearchIndex
) -> None:
    """C-19a、C-20(a): `last_seen_at` の Update が先に入る。読み直して要約を載せ直す。"""
    seed_pending(search_index)
    search_index.behavior.before(
        ops.REPLACE, lambda: change_during(search_index, last_seen_at="2026-11-10T00:00:00.000Z")
    )

    outcome = processor.process(DOCUMENT_ID)

    assert outcome is SummaryOutcome.WRITTEN
    stored = source_of(search_index, DOCUMENT_ID)
    assert stored["summary_status"] == "generated"
    assert stored["last_seen_at"] == "2026-11-10T00:00:00.000Z"
    assert replace_count(search_index) == 2


def test_last_seen_at_update_after_the_write_back_keeps_the_summary(
    processor: SummaryProcessor, search_index: InMemorySearchIndex
) -> None:
    """C-20(b): PUT が先に入り、Update はそのあとに読んで max を書く。要約も新しい値も残る。"""
    seed_pending(search_index)
    processor.process(DOCUMENT_ID)

    search_index.raise_last_seen_at(DOCUMENT_ID, datetime(2026, 11, 10, tzinfo=UTC))

    stored = source_of(search_index, DOCUMENT_ID)
    assert stored["summary_status"] == "generated"
    assert stored["last_seen_at"] == "2026-11-10T00:00:00.000Z"


def test_conflicts_up_to_the_reread_limit_still_write(
    processor: SummaryProcessor, search_index: InMemorySearchIndex
) -> None:
    seed_pending(search_index)
    search_index.behavior.inject(ops.REPLACE, Conflict(), times=MAX_REREADS)

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.WRITTEN
    assert replace_count(search_index) == MAX_REREADS + 1


def test_conflicts_beyond_the_reread_limit_leave_the_document_pending(
    processor: SummaryProcessor,
    search_index: InMemorySearchIndex,
    llm: FakeLlmClient,
    sleeps: list[float],
) -> None:
    """C-19b: 読み直しの上限を超えたら書き戻さず `pending` のまま残す(再走査の対象)。

    書き戻しは試行回数の上限まで繰り返す(生成した要約は使い回し、LLM は呼び直さない)。
    """
    seed_pending(search_index)
    search_index.behavior.inject(ops.REPLACE, Conflict(), times=None)

    outcome = processor.process(DOCUMENT_ID)

    assert outcome is SummaryOutcome.LEFT_PENDING
    assert source_of(search_index, DOCUMENT_ID)["summary_status"] == "pending"
    assert "summary" not in source_of(search_index, DOCUMENT_ID)
    assert replace_count(search_index) == MAX_ATTEMPTS * (MAX_REREADS + 1)
    assert len(llm.prompts) == 1
    assert sleeps == [1.0, 2.0]


def test_already_generated_by_another_writer_is_discarded_after_a_conflict(
    processor: SummaryProcessor, search_index: InMemorySearchIndex
) -> None:
    """C-19b: 読み直しで `pending` でなければ破棄する(`generated` を別の生成結果で上書きしない)。"""
    seed_pending(search_index)
    search_index.behavior.before(
        ops.REPLACE,
        lambda: change_during(
            search_index, summary="from another worker", summary_status="generated"
        ),
    )

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.DISCARDED
    assert source_of(search_index, DOCUMENT_ID)["summary"] == "from another worker"


def test_hash_mismatch_found_by_the_reread_is_discarded(
    processor: SummaryProcessor, search_index: InMemorySearchIndex
) -> None:
    """C-19b: 読み直しでハッシュが生成元と一致しなければ破棄する。"""
    seed_pending(search_index)
    search_index.behavior.before(
        ops.REPLACE, lambda: change_during(search_index, text_hash="n" * 64)
    )

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.DISCARDED
    assert "summary" not in source_of(search_index, DOCUMENT_ID)


def test_document_deleted_between_the_read_and_the_put_is_discarded_not_recreated(
    processor: SummaryProcessor, search_index: InMemorySearchIndex
) -> None:
    """C-19c: PUT の応答が文書なしなら、読み直して破棄する(文書を作らない。エラーにしない)。"""
    seed_pending(search_index)
    search_index.behavior.before(ops.REPLACE, lambda: search_index.seed_removal(DOCUMENT_ID))

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.DISCARDED
    assert search_index.document_ids() == []


def test_rejected_write_is_not_retried(
    processor: SummaryProcessor,
    search_index: InMemorySearchIndex,
    llm: FakeLlmClient,
    sleeps: list[float],
) -> None:
    """文書固有の拒否は繰り返しても直らない。`pending` のまま残す。"""
    seed_pending(search_index)
    search_index.behavior.inject(ops.REPLACE, Rejected("mapper_parsing_exception"), times=None)

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.LEFT_PENDING
    assert replace_count(search_index) == 1
    assert len(llm.prompts) == 1
    assert sleeps == []


# --- メンテナンス(L-9、案11) ---


def test_maintenance_flag_stops_before_generation_and_leaves_the_document_pending(
    processor: SummaryProcessor,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
    llm: FakeLlmClient,
    sleeps: list[float],
) -> None:
    """L-9: フラグが立っていれば、LLM を呼ばず(生成して捨てない)、書き込まずに止まる。"""
    seed_pending(search_index)
    set_maintenance(jobs_store, enabled=True)

    outcome = processor.process(DOCUMENT_ID)

    assert outcome is SummaryOutcome.PAUSED_BY_MAINTENANCE
    assert outcome.needs_rescan
    assert llm.prompts == []
    assert sleeps == []
    assert search_index.write_calls() == []
    assert source_of(search_index, DOCUMENT_ID)["summary_status"] == "pending"


@pytest.mark.parametrize("body", MALFORMED_MAINTENANCE_BODIES)
def test_a_malformed_maintenance_flag_stops_the_summary_like_an_enabled_one(  # fail-closed(0014)
    processor: SummaryProcessor,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
    llm: FakeLlmClient,
    body: dict[str, object],
) -> None:
    seed_pending(search_index)
    set_malformed_maintenance(jobs_store, body)

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.PAUSED_BY_MAINTENANCE
    assert llm.prompts == []
    assert search_index.write_calls() == []
    assert source_of(search_index, DOCUMENT_ID)["summary_status"] == "pending"


@pytest.mark.parametrize("body", MALFORMED_MAINTENANCE_BODIES)
def test_a_flag_turning_malformed_during_generation_stops_the_write(  # fail-closed(0014)
    processor: SummaryProcessor,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
    llm: FakeLlmClient,
    body: dict[str, object],
) -> None:
    seed_pending(search_index)
    llm.on_generate = lambda _prompt: set_malformed_maintenance(jobs_store, body)

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.PAUSED_BY_MAINTENANCE
    assert search_index.write_calls() == []


def test_repeated_requests_during_maintenance_never_call_the_llm(
    processor: SummaryProcessor,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
    llm: FakeLlmClient,
) -> None:
    """メンテナンスが続く間、依頼が何度来ても LLM を叩かない(全件を生成し直さない)。"""
    seed_pending(search_index)
    set_maintenance(jobs_store, enabled=True)

    outcomes = [processor.process(DOCUMENT_ID) for _ in range(5)]

    assert outcomes == [SummaryOutcome.PAUSED_BY_MAINTENANCE] * 5
    assert llm.prompts == []


def test_a_document_that_is_not_pending_is_discarded_even_during_maintenance(
    processor: SummaryProcessor,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
) -> None:
    """再走査を要請し続けないよう、生成の対象でない依頼は、メンテナンス中でも破棄にする。"""
    seed_pending(search_index, summary_status="generated", summary="s")
    set_maintenance(jobs_store, enabled=True)

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.DISCARDED


def test_flag_raised_during_generation_stops_the_write(
    processor: SummaryProcessor,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
    llm: FakeLlmClient,
) -> None:
    """フラグは書き込みの直前に確認する。生成中に立てば、書き込まない。"""
    seed_pending(search_index)
    llm.on_generate = lambda _prompt: set_maintenance(jobs_store, enabled=True)

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.PAUSED_BY_MAINTENANCE
    assert search_index.write_calls() == []


def test_the_same_document_is_summarized_after_the_flag_is_lowered(
    processor: SummaryProcessor,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
    llm: FakeLlmClient,
) -> None:
    seed_pending(search_index)
    set_maintenance(jobs_store, enabled=True)
    processor.process(DOCUMENT_ID)

    set_maintenance(jobs_store, enabled=False)

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.WRITTEN
    assert source_of(search_index, DOCUMENT_ID)["summary_status"] == "generated"
    assert len(llm.prompts) == 1  # 解除後の 1 回だけ


# --- LLM の失敗・再試行(案12、隔離) ---


def test_llm_failures_up_to_the_attempt_limit_leave_the_document_pending(
    processor: SummaryProcessor,
    search_index: InMemorySearchIndex,
    llm: FakeLlmClient,
    sleeps: list[float],
) -> None:
    """LLM の失敗は例外にせず、試行回数の上限まで再試行し、`pending` のまま残す。"""
    seed_pending(search_index)
    for _ in range(MAX_ATTEMPTS):
        llm.queue_result(LlmFailure(LlmFailureKind.TIMEOUT))

    outcome = processor.process(DOCUMENT_ID)

    assert outcome is SummaryOutcome.LEFT_PENDING
    assert len(llm.prompts) == MAX_ATTEMPTS
    assert sleeps == [1.0, 2.0]
    assert source_of(search_index, DOCUMENT_ID)["summary_status"] == "pending"
    assert search_index.write_calls() == []


def test_success_after_a_failure_writes_the_summary(
    processor: SummaryProcessor,
    search_index: InMemorySearchIndex,
    llm: FakeLlmClient,
    sleeps: list[float],
) -> None:
    seed_pending(search_index)
    llm.queue_result(LlmFailure(LlmFailureKind.CONNECTION))

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.WRITTEN
    assert len(llm.prompts) == 2
    assert sleeps == [1.0]


def test_backoff_grows_by_the_factor_up_to_the_maximum(
    make_processor,
    config: SummarizationConfig,
    search_index: InMemorySearchIndex,
    llm: FakeLlmClient,
    sleeps: list[float],
) -> None:
    seed_pending(search_index)
    for _ in range(4):
        llm.queue_result(LlmFailure(LlmFailureKind.PROVIDER_ERROR))

    make_processor(replace(config, max_attempts=5)).process(DOCUMENT_ID)

    assert sleeps == [1.0, 2.0, 3.0, 3.0]  # 上限 3.0 秒


def test_stop_request_abandons_the_remaining_llm_attempts(
    make_processor,
    search_index: InMemorySearchIndex,
    llm: FakeLlmClient,
    sleeps: list[float],
) -> None:
    """停止の要請があれば、バックオフのあとの残りの試行をしない(停止を試行回数分も待たせない)。"""
    seed_pending(search_index)
    stop_requested = threading.Event()
    llm.on_generate = lambda _prompt: stop_requested.set()
    for _ in range(MAX_ATTEMPTS):
        llm.queue_result(LlmFailure(LlmFailureKind.TIMEOUT))

    outcome = make_processor(should_stop=stop_requested.is_set).process(DOCUMENT_ID)

    assert outcome is SummaryOutcome.LEFT_PENDING
    assert len(llm.prompts) == 1
    # 待ってから止まっても、待つ前に止まっても、残りの試行をしないことが要点。
    assert sleeps in ([], [1.0])
    assert source_of(search_index, DOCUMENT_ID)["summary_status"] == "pending"


def test_stop_request_during_generation_still_writes_the_finished_summary(
    make_processor, search_index: InMemorySearchIndex, llm: FakeLlmClient
) -> None:
    """実行中の生成と書き戻しは終える(最初の試行は、停止の要請があっても行う)。"""
    seed_pending(search_index)
    stop_requested = threading.Event()
    llm.on_generate = lambda _prompt: stop_requested.set()

    outcome = make_processor(should_stop=stop_requested.is_set).process(DOCUMENT_ID)

    assert outcome is SummaryOutcome.WRITTEN


def test_stop_request_abandons_the_remaining_write_attempts(
    make_processor, search_index: InMemorySearchIndex, llm: FakeLlmClient
) -> None:
    seed_pending(search_index)
    stop_requested = threading.Event()
    llm.on_generate = lambda _prompt: stop_requested.set()
    search_index.behavior.inject(ops.REPLACE, Conflict(), times=None)

    outcome = make_processor(should_stop=stop_requested.is_set).process(DOCUMENT_ID)

    assert outcome is SummaryOutcome.LEFT_PENDING
    assert replace_count(search_index) == MAX_REREADS + 1  # 1 回目の試行だけ(読み直しを含む)


def test_empty_summary_text_counts_as_a_failed_attempt(
    processor: SummaryProcessor, search_index: InMemorySearchIndex, llm: FakeLlmClient
) -> None:
    seed_pending(search_index)
    for _ in range(MAX_ATTEMPTS):
        llm.queue_result(LlmCompletion(text="  \n", model="m"))

    assert processor.process(DOCUMENT_ID) is SummaryOutcome.LEFT_PENDING
    assert "summary" not in source_of(search_index, DOCUMENT_ID)


def test_failure_logs_never_contain_the_body_or_the_prompt(
    processor: SummaryProcessor,
    search_index: InMemorySearchIndex,
    llm: FakeLlmClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """R9: ログに本文を出さない。"""
    sentinel = "SECRET-BODY-SENTINEL"
    seed_pending(search_index, content=sentinel)
    for _ in range(MAX_ATTEMPTS):
        llm.queue_result(LlmFailure(LlmFailureKind.PROVIDER_ERROR))
    search_index.behavior.inject(ops.REPLACE, Rejected("mapper_parsing_exception"))

    with caplog.at_level(logging.DEBUG):
        processor.process(DOCUMENT_ID)
    seed_pending(search_index, content=sentinel)
    llm.queue_result(LlmCompletion(text="ok", model="m"))
    with caplog.at_level(logging.DEBUG):
        processor.process(DOCUMENT_ID)

    assert caplog.records
    assert sentinel not in caplog.text


# --- OpenSearch の全体異常 ---


@pytest.mark.parametrize("operation", [ops.FETCH, ops.REPLACE])
def test_whole_index_failure_propagates_and_leaves_the_document_pending(
    processor: SummaryProcessor, search_index: InMemorySearchIndex, operation: str
) -> None:
    seed_pending(search_index)
    search_index.behavior.inject(operation, OpenSearchUnavailableError("http_503"))

    with pytest.raises(UnavailableError):
        processor.process(DOCUMENT_ID)

    assert source_of(search_index, DOCUMENT_ID)["summary_status"] == "pending"
