"""削除結果の窓口(終端遷移ヘルパー、保持件数、先行の判定、409 の読み直し)。

D-13・D-41・D-42(ID 一覧の削除と、ダイジェストが残ること。K35)、D-45(保持件数)、D-46(先行の順序)。
P4 の deletion が使う入口なので、契約をここで固定する。
"""

import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from loreley_indexer.common.errors import UnavailableError
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionResults,
    DeletionStatus,
    MalformedRecordError,
    deletion_record_id,
    deletion_result_record_id,
    retry_after_conflict,
)
from loreley_indexer.crawl_runs.lifecycle.results import queue_order_key
from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    NotFound,
    OpenSearchUnavailableError,
    OpenSearchUnexpectedResponseError,
    Rejected,
    Written,
)
from tests.crawl_runs.factories import (
    MALFORMED_VALUE,
    SOURCE_ID,
    hex_id,
    make_generation,
    make_result,
    seed_malformed_result,
    seed_result,
    snapshot,
    stored_result,
)
from tests.crawl_runs.lifecycle.conftest import RETENTION_COUNT
from tests.fakes import in_memory_store as ops
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.in_memory_store import InMemoryStore

T0 = datetime(2026, 11, 9, 1, 20, 5, tzinfo=UTC)


def waiting_result(crawl_id: str = "job-a", **overrides: object):
    defaults: dict[str, object] = {
        "finish_received_at": T0,
        "finish_request_digest": "d" * 64,
        "skipped_document_ids": (hex_id(1),),
        "oversize_document_ids": (hex_id(2),),
        "skip_and_oversize_id_count": 2,
        "skip_and_oversize_id_limit_exceeded": False,
        "e_missing": 1,
    }
    return make_result(crawl_id=crawl_id, **{**defaults, **overrides})


# --- 終端遷移(K35) ---


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (DeletionStatus.DELETED, None),
        (DeletionStatus.SKIPPED_BY_RATIO, None),
        (DeletionStatus.VALIDATION_FAILED, DeletionReason.COUNT_MISMATCH),
        (DeletionStatus.DISCARDED, DeletionReason.SOURCE_DELETED),
        (DeletionStatus.FAILED, DeletionReason.MAINTENANCE),
    ],
)
def test_terminal_transition_drops_the_id_lists_and_keeps_the_digest(  # D-13、D-41、D-42
    results: DeletionResults,
    deletions_store: InMemoryStore,
    status: DeletionStatus,
    reason: DeletionReason | None,
) -> None:
    seed_result(deletions_store, waiting_result())
    current = results.fetch_result("job-a")

    outcome = results.transition_to_terminal(current, status, reason=reason)

    assert isinstance(outcome, Written)
    result = stored_result(deletions_store, "job-a")
    assert (result.status, result.reason) == (status, reason)
    assert result.ended_at == DEFAULT_NOW
    assert result.skipped_document_ids is None
    assert result.oversize_document_ids is None
    assert result.finish_request_digest == "d" * 64
    assert result.finish_received_at == T0
    assert result.e_missing == 1  # 件数照合の結果は残る
    assert result.skip_and_oversize_id_count == 2
    assert deletions_store.write_calls() == [ops.REPLACE]  # 一覧の削除は同じ書き込み


def test_terminal_transition_records_the_detail_and_the_progress(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, waiting_result())
    current = results.fetch_result("job-a")

    results.transition_to_terminal(
        current,
        DeletionStatus.FAILED,
        reason=DeletionReason.DELETE_ERROR,
        reason_detail="timeout",
        progress=replace(current.record, deleted_count=7),
    )

    result = stored_result(deletions_store, "job-a")
    assert (result.reason, result.reason_detail, result.deleted_count) == (
        DeletionReason.DELETE_ERROR,
        "timeout",
        7,
    )


def test_terminal_transition_rejects_a_non_terminal_status(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, waiting_result())
    with pytest.raises(ValueError):
        results.transition_to_terminal(results.fetch_result("job-a"), DeletionStatus.RUNNING)


def test_terminal_transition_with_a_stale_version_is_a_conflict_and_writes_nothing(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, waiting_result())
    current = results.fetch_result("job-a")
    discarded = waiting_result(
        status=DeletionStatus.DISCARDED, reason=DeletionReason.SOURCE_DELETED
    )
    seed_result(deletions_store, discarded)  # 別の書き手(ソース削除)が先に終端にした

    outcome = results.transition_to_terminal(current, DeletionStatus.DELETED)

    assert outcome == Conflict()
    assert stored_result(deletions_store, "job-a").reason is DeletionReason.SOURCE_DELETED


def test_terminal_transition_of_a_vanished_result_is_not_found(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, waiting_result())
    current = results.fetch_result("job-a")
    deletions_store.delete(deletion_result_record_id("job-a"))

    assert results.transition_to_terminal(current, DeletionStatus.DELETED) == NotFound()
    assert deletions_store.record_ids() == []


def test_non_terminal_update_keeps_the_status_and_the_id_lists(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    """`deletion_started_at` などの進捗の更新(終端でない)。ID 一覧は判定のために残す。"""
    seed_result(deletions_store, waiting_result())
    current = results.fetch_result("job-a")

    outcome = results.replace_result(current, replace(current.record, deletion_started_at=T0))

    assert isinstance(outcome, Written)
    result = stored_result(deletions_store, "job-a")
    assert result.status is DeletionStatus.RUNNING
    assert result.deletion_started_at == T0
    assert result.skipped_document_ids == (hex_id(1),)


def test_rejected_writes_are_unexpected_errors(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, waiting_result())
    current = results.fetch_result("job-a")
    deletions_store.behavior.inject(ops.REPLACE, Rejected("mapper_parsing_exception"))
    with pytest.raises(OpenSearchUnexpectedResponseError):
        results.replace_result(current, current.record)

    deletions_store.behavior.inject(ops.SAVE, Rejected("mapper_parsing_exception"))
    with pytest.raises(OpenSearchUnexpectedResponseError):
        results.create_result(make_result(crawl_id="job-new"))


# --- 保持件数(U-2、D-45) ---


def seed_terminal(store: InMemoryStore, crawl_id: str, ended_at: datetime, **overrides: object):
    seed_result(
        store,
        make_result(
            crawl_id=crawl_id, status=DeletionStatus.DELETED, ended_at=ended_at, **overrides
        ),
    )


def test_terminal_results_over_the_retention_count_are_deleted_oldest_first(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    for number in range(RETENTION_COUNT + 2):
        seed_terminal(deletions_store, f"job-{number}", T0 + timedelta(minutes=number))

    results.prune_terminal_results(SOURCE_ID)

    remaining = sorted(deletions_store.record_ids())
    assert remaining == [deletion_result_record_id(f"job-{n}") for n in (2, 3, 4)]


def test_nothing_is_deleted_up_to_the_retention_count(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    for number in range(RETENTION_COUNT):
        seed_terminal(deletions_store, f"job-{number}", T0 + timedelta(minutes=number))

    results.prune_terminal_results(SOURCE_ID)

    assert deletions_store.write_calls() == []
    assert len(deletions_store.record_ids()) == RETENTION_COUNT


def test_running_results_are_neither_counted_nor_deleted(  # D-45
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    for number in range(RETENTION_COUNT):
        seed_terminal(deletions_store, f"job-done-{number}", T0 + timedelta(minutes=number))
    seed_result(deletions_store, make_result(crawl_id="job-unfinished"))
    seed_result(deletions_store, waiting_result("job-waiting"))

    results.prune_terminal_results(SOURCE_ID)

    assert len(deletions_store.record_ids()) == RETENTION_COUNT + 2  # 何も消えない
    seed_terminal(deletions_store, "job-done-new", T0 + timedelta(hours=1))
    results.prune_terminal_results(SOURCE_ID)
    remaining = set(deletions_store.record_ids())
    assert deletion_result_record_id("job-done-0") not in remaining  # 終端の古いものだけ
    assert deletion_result_record_id("job-unfinished") in remaining
    assert deletion_result_record_id("job-waiting") in remaining


def test_retention_is_per_source_and_leaves_other_records_alone(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    for number in range(RETENTION_COUNT + 1):
        seed_terminal(deletions_store, f"job-{number}", T0 + timedelta(minutes=number))
    seed_terminal(deletions_store, "job-other", T0 - timedelta(days=9), source_id="src-other")
    deletions_store.seed(deletion_record_id(SOURCE_ID), make_generation().to_body())

    results.prune_terminal_results(SOURCE_ID)

    remaining = set(deletions_store.record_ids())
    assert deletion_result_record_id("job-0") not in remaining
    assert deletion_result_record_id("job-other") in remaining  # 別ソースは数えない
    assert deletion_record_id(SOURCE_ID) in remaining  # 世代の記録は整理の対象外


def test_equal_ended_at_and_started_at_is_ordered_by_crawl_id(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    """固定時計でも、残す順序が決定的になる(新しい順: ended_at、started_at、crawl_id)。"""
    for crawl_id in ("job-a", "job-b", "job-c", "job-d"):
        seed_terminal(deletions_store, crawl_id, T0)

    results.prune_terminal_results(SOURCE_ID)

    assert sorted(deletions_store.record_ids()) == [
        deletion_result_record_id(c) for c in ("job-b", "job-c", "job-d")
    ]


def test_equal_ended_at_is_ordered_by_started_at_before_crawl_id(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    """`ended_at` が同じなら、`started_at` が新しいものを残す(`crawl_id` が大きい順ではない)。"""
    started_at = {"job-a": 4, "job-b": 1, "job-c": 2, "job-d": 3}  # 新しい順: a、d、c、b
    for crawl_id, hours in started_at.items():
        seed_terminal(deletions_store, crawl_id, T0, started_at=T0 + timedelta(hours=hours))

    results.prune_terminal_results(SOURCE_ID)

    assert sorted(deletions_store.record_ids()) == [
        deletion_result_record_id(c) for c in ("job-a", "job-c", "job-d")
    ]


def test_a_failed_pruning_does_not_fail_the_terminal_transition(
    results: DeletionResults,
    deletions_store: InMemoryStore,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """整理(最後の掃除)は付随の処理。失敗しても、書き込み済みの終端遷移を失敗にしない。"""
    seed_result(deletions_store, waiting_result("job-a"))
    current = results.fetch_result("job-a")
    deletions_store.behavior.inject(
        ops.LIST, OpenSearchUnavailableError(f"http_503 {MALFORMED_VALUE}")
    )

    with caplog.at_level(logging.WARNING):
        outcome = results.transition_to_terminal(current, DeletionStatus.DELETED)

    assert isinstance(outcome, Written)
    assert stored_result(deletions_store, "job-a").status is DeletionStatus.DELETED
    assert "OpenSearchUnavailableError" in caplog.text
    assert MALFORMED_VALUE not in caplog.text  # 例外クラス名だけを出す(R9)


def test_an_unexpected_response_while_pruning_is_not_swallowed(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    """握るのは OpenSearch の全体異常(一時的な失敗)だけ。想定外の応答は異常として伝える。"""
    seed_result(deletions_store, waiting_result("job-a"))
    current = results.fetch_result("job-a")
    deletions_store.behavior.inject(
        ops.LIST, OpenSearchUnexpectedResponseError("parsing_exception")
    )

    with pytest.raises(OpenSearchUnexpectedResponseError):
        results.transition_to_terminal(current, DeletionStatus.DELETED)


def test_a_terminal_transition_prunes_the_source(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    for number in range(RETENTION_COUNT):
        seed_terminal(deletions_store, f"job-done-{number}", T0 - timedelta(days=number + 1))
    seed_result(deletions_store, waiting_result("job-a"))

    results.transition_to_terminal(results.fetch_result("job-a"), DeletionStatus.DELETED)

    assert deletion_result_record_id("job-done-2") not in deletions_store.record_ids()
    assert deletion_result_record_id("job-a") in deletions_store.record_ids()


def test_a_conflicting_transition_does_not_prune(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    for number in range(RETENTION_COUNT + 1):
        seed_terminal(deletions_store, f"job-done-{number}", T0 + timedelta(minutes=number))
    seed_result(deletions_store, waiting_result("job-a"))
    current = results.fetch_result("job-a")
    seed_result(deletions_store, waiting_result("job-a", deletion_started_at=T0))

    assert results.transition_to_terminal(current, DeletionStatus.DELETED) == Conflict()
    assert len(deletions_store.record_ids()) == RETENTION_COUNT + 2


# --- 形式が不正な記録(A6) ---

LISTERS = {
    "unfinished_received": (
        lambda results: results.list_unfinished_received(),
        {"finish_received_at": T0},
    ),
    "non_terminal": (lambda results: results.list_non_terminal(SOURCE_ID), {}),
    "running_without_finish": (
        lambda results: results.list_running_without_finish(SOURCE_ID),
        {},
    ),
}


@pytest.mark.parametrize("lister_name", LISTERS)
def test_a_malformed_record_is_left_out_of_the_listing_and_only_its_id_is_logged(
    results: DeletionResults,
    deletions_store: InMemoryStore,
    caplog: pytest.LogCaptureFixture,
    lister_name: str,
) -> None:
    """1 件の不正で一覧全体が失敗しない(起動時の整理や走査が、再起動のたびに落ちない)。"""
    lister, extra = LISTERS[lister_name]
    seed_result(deletions_store, make_result(crawl_id="job-good", **extra))
    bad_record_id = seed_malformed_result(deletions_store, crawl_id="job-bad", **extra)
    before = snapshot(deletions_store)

    with caplog.at_level(logging.WARNING):
        listed = lister(results)

    assert [record.crawl_id for record in listed] == ["job-good"]
    assert bad_record_id in caplog.text
    assert MALFORMED_VALUE not in caplog.text  # 記録の中身は出さない(R9)
    assert snapshot(deletions_store) == before  # 読まない・書き換えない


def test_a_malformed_record_is_warned_once_per_process_and_then_only_debugged(
    results: DeletionResults, deletions_store: InMemoryStore, caplog: pytest.LogCaptureFixture
) -> None:
    """走査のたびに同じ WARNING が出続けない(約 2 秒ごとの洪水を避ける)。"""
    received = {"finish_received_at": DEFAULT_NOW}  # どちらの一覧にも載る
    first_bad = seed_malformed_result(deletions_store, crawl_id="job-bad-1", **received)
    second_bad = seed_malformed_result(deletions_store, crawl_id="job-bad-2", **received)

    with caplog.at_level(logging.DEBUG):
        for _ in range(3):
            results.list_unfinished_received()
            results.list_non_terminal(SOURCE_ID)

    def levels_of(record_id: str) -> list[int]:
        return [r.levelno for r in caplog.records if record_id in r.getMessage()]

    # 各記録について、最初の 1 回だけ WARNING。以降(別の一覧メソッドを含む)は DEBUG。
    assert levels_of(first_bad).count(logging.WARNING) == 1
    assert levels_of(second_bad).count(logging.WARNING) == 1
    assert levels_of(first_bad)[0] == logging.WARNING
    assert set(levels_of(first_bad)[1:]) == {logging.DEBUG}
    assert len(levels_of(first_bad)) == 6


def test_a_new_process_warns_about_a_malformed_record_again(
    deletions_store: InMemoryStore, caplog: pytest.LogCaptureFixture
) -> None:
    seed_malformed_result(deletions_store, crawl_id="job-bad")

    with caplog.at_level(logging.WARNING):
        for _ in range(2):  # プロセスの再起動を、新しい `DeletionResults` で表す
            DeletionResults(
                deletions_store, retention_count=3, clock=FixedClock()
            ).list_non_terminal(SOURCE_ID)

    assert [r.levelno for r in caplog.records] == [logging.WARNING, logging.WARNING]


def test_a_malformed_record_read_by_id_still_raises() -> None:
    """ID を指定した読み取りは、不正な記録を無いものとして黙って扱わない。"""
    store = InMemoryStore()
    results = DeletionResults(store, retention_count=3, clock=FixedClock())
    seed_malformed_result(store, crawl_id="job-bad")

    with pytest.raises(MalformedRecordError):
        results.fetch_result("job-bad")


# --- 先行する削除結果(arch 9.9 項 6。D-46) ---


def test_preceding_results_are_in_acceptance_order_and_exclude_self_and_later_ones(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    for crawl_id, offset in (("job-c", 120), ("job-a", 0), ("job-b", 60), ("job-d", 180)):
        seed_result(
            deletions_store,
            make_result(
                crawl_id=crawl_id,
                finish_received_at=T0 + timedelta(seconds=offset),
                finish_request_digest="d" * 64,
            ),
        )

    preceding = results.preceding_results(stored_result(deletions_store, "job-c"))

    assert [record.crawl_id for record in preceding] == ["job-a", "job-b"]


def test_preceding_results_exclude_terminal_ones_other_sources_and_unreceived(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    seed_result(
        deletions_store,
        make_result(
            crawl_id="job-done",
            status=DeletionStatus.DELETED,
            finish_received_at=T0,
            finish_request_digest="d" * 64,
        ),
    )
    seed_result(
        deletions_store,
        make_result(crawl_id="job-other", source_id="src-other", finish_received_at=T0),
    )
    seed_result(deletions_store, make_result(crawl_id="job-unreceived"))
    seed_result(
        deletions_store, waiting_result("job-me", finish_received_at=T0 + timedelta(hours=1))
    )

    assert results.preceding_results(stored_result(deletions_store, "job-me")) == []


def test_a_result_without_finish_has_no_predecessors_and_no_queue_position(
    results: DeletionResults,
) -> None:
    unreceived = make_result()
    assert results.preceding_results(unreceived) == []
    with pytest.raises(ValueError):
        queue_order_key(unreceived)


# --- P4 の入口: ソース削除 1・3 が使う(arch 9.14) ---


def test_non_terminal_results_of_the_source_include_waiting_and_unreceived_ones(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result(crawl_id="job-unreceived"))
    seed_result(deletions_store, waiting_result("job-waiting"))
    seed_result(deletions_store, waiting_result("job-judging", deletion_started_at=T0))
    seed_result(deletions_store, make_result(crawl_id="job-done", status=DeletionStatus.DELETED))
    seed_result(deletions_store, make_result(crawl_id="job-other", source_id="src-other"))

    non_terminal = results.list_non_terminal(SOURCE_ID)

    assert sorted(record.crawl_id for record in non_terminal) == [
        "job-judging",
        "job-unreceived",
        "job-waiting",
    ]


def test_deleting_the_source_records_removes_the_generation_and_every_result_of_the_source(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    deletions_store.seed(deletion_record_id(SOURCE_ID), make_generation().to_body())
    seed_result(deletions_store, make_result(crawl_id="job-a"))
    seed_result(deletions_store, make_result(crawl_id="job-b", status=DeletionStatus.DELETED))
    deletions_store.seed(
        deletion_record_id("src-other"), make_generation(source_id="src-other").to_body()
    )
    seed_result(deletions_store, make_result(crawl_id="job-other", source_id="src-other"))

    assert results.delete_source_records(SOURCE_ID) is True

    assert deletions_store.record_ids() == [
        deletion_record_id("src-other"),
        deletion_result_record_id("job-other"),
    ]


def test_deleting_the_source_records_is_idempotent(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result())

    assert results.delete_source_records(SOURCE_ID) is True
    assert results.delete_source_records(SOURCE_ID) is False
    assert deletions_store.record_ids() == []


def test_a_rejected_delete_of_a_source_record_is_an_unexpected_response(
    results: DeletionResults, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result())
    deletions_store.behavior.inject(ops.DELETE, Rejected("security_exception"), times=1)

    with pytest.raises(OpenSearchUnexpectedResponseError):
        results.delete_source_records(SOURCE_ID)


# --- 読み直しの繰り返し ---


def test_retry_after_conflict_returns_the_first_non_conflict_result() -> None:
    attempts: list[int] = []

    def attempt():
        attempts.append(1)
        return Conflict() if len(attempts) < 3 else "done"

    assert retry_after_conflict(attempt, max_rereads=2) == "done"
    assert len(attempts) == 3


def test_retry_after_conflict_stops_after_the_initial_attempt_and_the_rereads() -> None:
    attempts: list[int] = []

    def attempt():
        attempts.append(1)
        return Conflict()

    with pytest.raises(UnavailableError) as error:
        retry_after_conflict(attempt, max_rereads=3)

    assert len(attempts) == 4
    assert error.value.reason == "write_conflict"


def test_retry_after_conflict_does_not_retry_without_a_conflict() -> None:
    attempts: list[int] = []

    def attempt():
        attempts.append(1)
        return None

    assert retry_after_conflict(attempt, max_rereads=3) is None
    assert len(attempts) == 1


def test_generation_record_roundtrip_is_used_for_the_conflict_check(
    results: DeletionResults, deletions_store: InMemoryStore, clock: FixedClock
) -> None:
    """世代の更新は、無ければ作成、あれば読んだ版を条件にした置き換え。"""
    record = replace(make_generation(), updated_at=clock.now())

    assert isinstance(results.replace_generation(None, record), Written)
    stored = results.fetch_generation(SOURCE_ID)
    assert stored is not None
    deletions_store.seed(deletion_record_id(SOURCE_ID), record.to_body())  # 別の書き手

    assert results.replace_generation(stored, record) == Conflict()
