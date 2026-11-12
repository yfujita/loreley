"""削除の実行(arch 9.8、9.7 順6)。

D-9・D-19・D-33(実行側)・D-44・D-86・D-87・D-88・D-89 と、自分の結果が終端状態・404 になったときの
停止(D-41 の実行側)、書き込みの 409 の読み直し(R8)を確認する。
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest

from loreley_indexer.common.errors import UnavailableError
from loreley_indexer.crawl_runs import DeletionManager, DeletionOutcome, create_deletion_manager
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionResults,
    DeletionStatus,
    deletion_result_record_id,
)
from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    NotFound,
    OpenSearchUnavailableError,
    Rejected,
)
from tests.crawl_runs.deletion.conftest import BATCH_SIZE, MAX_REREADS, RETRY_ATTEMPTS
from tests.crawl_runs.deletion.scenario import (
    EXPIRED_AT,
    OTHER_SOURCE_ID,
    Scenario,
    document_source,
    fail_the_maintenance_check_at,
    process,
    raise_the_maintenance_flag_at_check,
    remaining,
    seed_scenario,
)
from tests.crawl_runs.factories import CRAWL_ID, SOURCE_ID, stored_result
from tests.documents.factories import MALFORMED_MAINTENANCE_BODIES, set_maintenance
from tests.fakes import in_memory_search_index as index_ops
from tests.fakes import in_memory_store as store_ops
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore

RESULT_ID = deletion_result_record_id(CRAWL_ID)


@pytest.fixture
def seven_targets(search_index: InMemorySearchIndex, deletions_store: InMemoryStore) -> Scenario:
    """バッチサイズ 3 で 3・3・1 の 3 バッチになる対象(最小件数ルールで必ず削除される)。"""
    return seed_scenario(
        search_index, deletions_store, seen=4, expired=7, min_delete_count=100, enumerated_count=4
    )


def freshen(search_index: InMemorySearchIndex, document_id: str) -> None:
    """新しいクロールが `last_seen_at` を更新した(別の書き手による書き込みの再現)。"""
    search_index.seed(document_id, document_source(SOURCE_ID, DEFAULT_NOW))


# --- バッチと進捗(D-9、案 18) ---


def test_documents_are_deleted_by_batch_and_the_progress_is_recorded_before_each_batch(  # D-9
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    stored_before_each_write: list[tuple[int | None, int | None]] = []

    def record_stored_progress() -> None:
        stored = stored_result(deletions_store)
        stored_before_each_write.append((stored.deleted_count, stored.target_count))

    # 書き込みは、`deletion_started_at`、バッチ 3 回の進捗、終端状態の 5 回。
    for _ in range(5):
        deletions_store.behavior.before(store_ops.REPLACE, record_stored_progress, key=RESULT_ID)

    outcome = process(manager)

    assert outcome is DeletionOutcome.FINISHED
    assert stored_before_each_write == [(None, None), (None, None), (0, 7), (3, 7), (6, 7)]
    result = stored_result(deletions_store)
    assert (result.status, result.deleted_count, result.target_count) == (
        DeletionStatus.DELETED,
        7,
        7,
    )
    assert remaining(search_index, seven_targets.expired) == set()
    assert remaining(search_index, seven_targets.seen) == set(seven_targets.seen)


def test_each_document_is_read_again_and_deleted_with_the_version_it_read(  # D-9
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=0, expired=2)

    process(manager)

    document_operations = [
        (call.operation, call.key)
        for call in search_index.behavior.calls_of(index_ops.FETCH_FOR_DELETION, index_ops.DELETE)
    ]
    assert document_operations == [
        (index_ops.FETCH_FOR_DELETION, scenario.expired[0]),
        (index_ops.DELETE, scenario.expired[0]),
        (index_ops.FETCH_FOR_DELETION, scenario.expired[1]),
        (index_ops.DELETE, scenario.expired[1]),
    ]


# --- TTL の再確認と競合(D-86、D-87、D-88、D-89) ---


def test_a_document_updated_during_the_id_collection_is_kept_and_not_counted(  # D-86
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
) -> None:
    scenario = seed_scenario(
        search_index, deletions_store, seen=0, expired=10, min_delete_count=100
    )
    # 2 ページ目の取り込みの前に、1 ページ目で取り込み済みの文書が更新される。
    search_index.behavior.before(index_ops.SEARCH_IDS, lambda: None)
    search_index.behavior.before(
        index_ops.SEARCH_IDS, lambda: freshen(search_index, scenario.expired[0])
    )

    process(manager)

    result = stored_result(deletions_store)
    assert (result.target_count, result.deleted_count) == (10, 9)  # 取りこぼし・重複なし。D <= T
    assert remaining(search_index, scenario.expired) == {scenario.expired[0]}


def test_a_document_updated_before_the_recheck_is_not_deleted(  # D-87(a)
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    updated = seven_targets.expired[4]
    search_index.behavior.before(
        index_ops.FETCH_FOR_DELETION, lambda: freshen(search_index, updated), key=updated
    )

    process(manager)

    result = stored_result(deletions_store)
    assert (result.status, result.target_count, result.deleted_count) == (
        DeletionStatus.DELETED,
        7,
        6,
    )
    assert remaining(search_index, seven_targets.expired) == {updated}


def test_a_document_updated_after_the_recheck_survives_the_conditional_delete(  # D-87(b)
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    updated = seven_targets.expired[1]
    search_index.behavior.before(
        index_ops.DELETE, lambda: freshen(search_index, updated), key=updated
    )

    process(manager)

    result = stored_result(deletions_store)
    assert (result.status, result.deleted_count) == (DeletionStatus.DELETED, 6)
    # 条件付き削除が 409 になり、読み直した文書は TTL を満たさないので、削除しない。
    assert remaining(search_index, seven_targets.expired) == {updated}
    deletes_of_the_updated = [
        call for call in search_index.behavior.calls_of(index_ops.DELETE) if call.key == updated
    ]
    assert len(deletes_of_the_updated) == 1  # 読み直して TTL を満たさないので、再び削除しない


def test_an_update_that_keeps_last_seen_at_is_read_again_and_the_document_is_deleted(  # D-87(c)
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    updated = seven_targets.expired[1]

    def write_a_summary_back() -> None:
        # 要約の書き戻しなど: `last_seen_at` は変えず、版だけが進む。
        search_index.seed(updated, document_source(SOURCE_ID, EXPIRED_AT, summary="s"))

    search_index.behavior.before(index_ops.DELETE, write_a_summary_back, key=updated)

    process(manager)

    assert stored_result(deletions_store).deleted_count == 7
    assert remaining(search_index, seven_targets.expired) == set()
    # 409 のあとの読み直し(GET)と、読み直した版での再削除。
    keyed_calls = [
        call.operation
        for call in search_index.behavior.calls_of(index_ops.FETCH_FOR_DELETION, index_ops.DELETE)
        if call.key == updated
    ]
    assert keyed_calls == [
        index_ops.FETCH_FOR_DELETION,
        index_ops.DELETE,
        index_ops.FETCH_FOR_DELETION,
        index_ops.DELETE,
    ]


def test_a_conflict_beyond_the_reread_limit_leaves_the_document_for_the_next_run(  # D-88
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    stuck = seven_targets.expired[2]
    search_index.behavior.inject(index_ops.DELETE, Conflict(), key=stuck, times=1 + MAX_REREADS)

    process(manager)

    result = stored_result(deletions_store)
    # 結果は `deleted` のまま終了し、その文書は数えない(`failed` や `write_conflict` ではない)。
    assert (result.status, result.target_count, result.deleted_count) == (
        DeletionStatus.DELETED,
        7,
        6,
    )
    assert remaining(search_index, seven_targets.expired) == {stuck}


def test_a_conflict_within_the_reread_limit_is_resolved(  # D-88 の境界
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    search_index.behavior.inject(
        index_ops.DELETE, Conflict(), key=seven_targets.expired[2], times=MAX_REREADS
    )

    process(manager)

    assert stored_result(deletions_store).deleted_count == 7
    assert remaining(search_index, seven_targets.expired) == set()


def test_a_document_that_is_already_gone_is_skipped_without_an_error(  # D-89
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    gone_before_the_read, gone_before_the_delete = (
        seven_targets.expired[0],
        seven_targets.expired[5],
    )
    search_index.behavior.before(
        index_ops.FETCH_FOR_DELETION,
        lambda: search_index.seed_removal(gone_before_the_read),
        key=gone_before_the_read,
    )
    search_index.behavior.inject(
        index_ops.DELETE, NotFound(), key=gone_before_the_delete, times=1
    )  # 実機では削除時に `not_found` になる場合(未決。U-31)

    process(manager)

    result = stored_result(deletions_store)
    assert (result.status, result.target_count, result.deleted_count) == (
        DeletionStatus.DELETED,
        7,
        5,
    )


def test_a_document_of_another_source_is_never_deleted_even_if_its_id_was_a_target(
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    swapped = seven_targets.expired[3]
    search_index.behavior.before(
        index_ops.FETCH_FOR_DELETION,
        lambda: search_index.seed(swapped, document_source(OTHER_SOURCE_ID, EXPIRED_AT)),
        key=swapped,
    )

    process(manager)

    assert stored_result(deletions_store).deleted_count == 6
    assert remaining(search_index, (swapped,)) == {swapped}


@pytest.mark.parametrize(
    "unreadable",
    [{"source_id": SOURCE_ID}, {"source_id": SOURCE_ID, "last_seen_at": "not a date"}],
    ids=["no_last_seen_at", "invalid_last_seen_at"],
)
def test_a_document_whose_last_seen_at_cannot_be_read_is_not_deleted(
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
    unreadable: dict[str, Any],
) -> None:
    target = seven_targets.expired[0]
    search_index.behavior.before(
        index_ops.FETCH_FOR_DELETION, lambda: search_index.seed(target, unreadable), key=target
    )

    process(manager)

    assert stored_result(deletions_store).deleted_count == 6
    assert remaining(search_index, (target,)) == {target}


# --- メンテナンスフラグ(D-19、D-33) ---


def test_the_flag_raised_before_the_first_batch_stops_it(  # D-19
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    raise_the_maintenance_flag_at_check(jobs_store, 2)

    outcome = process(manager)

    result = stored_result(deletions_store)
    assert outcome is DeletionOutcome.FINISHED
    assert (result.status, result.reason) == (DeletionStatus.FAILED, DeletionReason.MAINTENANCE)
    assert result.deleted_count == 0
    assert (result.target_count, result.denominator) == (7, 11)  # 判定の数値は残る
    assert search_index.write_calls() == []
    assert result.skipped_document_ids is None


def test_the_flag_raised_between_batches_stops_before_the_next_batch(  # D-19、D-33
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    raise_the_maintenance_flag_at_check(jobs_store, 3)

    process(manager)

    result = stored_result(deletions_store)
    assert (result.status, result.reason) == (DeletionStatus.FAILED, DeletionReason.MAINTENANCE)
    assert result.deleted_count == BATCH_SIZE
    # 実行済みのバッチの分は削除済み、未実行の分は削除されない。
    assert remaining(search_index, seven_targets.expired) == set(seven_targets.expired[BATCH_SIZE:])


@pytest.mark.parametrize("nth_check", [2, 3], ids=["before_batch_1", "before_batch_2"])
@pytest.mark.parametrize("body", MALFORMED_MAINTENANCE_BODIES)
def test_a_flag_turning_malformed_stops_before_the_next_batch(  # fail-closed(0014)
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    seven_targets: Scenario,
    nth_check: int,
    body: dict[str, object],
) -> None:
    raise_the_maintenance_flag_at_check(jobs_store, nth_check, body=body)

    process(manager)

    result = stored_result(deletions_store)
    assert (result.status, result.reason) == (DeletionStatus.FAILED, DeletionReason.MAINTENANCE)
    deleted_count = (nth_check - 2) * BATCH_SIZE
    assert result.deleted_count == deleted_count
    assert remaining(search_index, seven_targets.expired) == set(
        seven_targets.expired[deleted_count:]
    )


def test_the_flag_in_the_middle_of_a_batch_does_not_stop_that_batch(  # 9.8(止まるのはバッチの単位)
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    search_index.behavior.before(
        index_ops.FETCH_FOR_DELETION,
        lambda: set_maintenance(jobs_store, enabled=True),
        key=seven_targets.expired[1],  # 1 バッチ目の 2 件目の前
    )

    process(manager)

    result = stored_result(deletions_store)
    assert (result.reason, result.deleted_count) == (DeletionReason.MAINTENANCE, BATCH_SIZE)


# --- 削除のエラー(D-44) ---


def test_a_persistent_delete_error_fails_the_deletion_with_the_progress_recorded(  # D-44
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
    sleeps: list[float],
) -> None:
    broken = seven_targets.expired[1]
    search_index.behavior.inject(
        index_ops.DELETE, OpenSearchUnavailableError("http_503"), key=broken, times=RETRY_ATTEMPTS
    )

    outcome = process(manager)

    result = stored_result(deletions_store)
    assert outcome is DeletionOutcome.FINISHED
    assert (result.status, result.reason) == (DeletionStatus.FAILED, DeletionReason.DELETE_ERROR)
    assert result.reason_detail == "unavailable:http_503"
    assert result.deleted_count == 1  # それまでの削除件数
    assert sleeps == [1.0, 2.0]  # 最初の 1 回 + 再試行 2 回の間のバックオフ
    assert remaining(search_index, seven_targets.expired) == set(seven_targets.expired[1:])
    assert result.skipped_document_ids is None


def test_a_delete_error_that_clears_within_the_attempts_does_not_fail_the_deletion(  # 4.4
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
    sleeps: list[float],
) -> None:
    flaky = seven_targets.expired[1]
    search_index.behavior.inject(
        index_ops.DELETE,
        OpenSearchUnavailableError("connection_timeout"),
        key=flaky,
        times=RETRY_ATTEMPTS - 1,
    )

    process(manager)

    assert stored_result(deletions_store).status is DeletionStatus.DELETED
    assert remaining(search_index, seven_targets.expired) == set()
    assert sleeps == [1.0, 2.0]


def test_an_error_while_rereading_the_document_is_retried_too(
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
    sleeps: list[float],
) -> None:
    search_index.behavior.inject(
        index_ops.FETCH_FOR_DELETION,
        OpenSearchUnavailableError("http_429"),
        key=seven_targets.expired[0],
        times=1,
    )

    process(manager)

    assert stored_result(deletions_store).deleted_count == 7
    assert sleeps == [1.0]


def test_a_document_specific_rejection_is_retried_and_then_recorded_by_its_type(  # D-44
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    search_index.behavior.inject(
        index_ops.DELETE,
        Rejected("illegal_argument_exception"),
        key=seven_targets.expired[0],
        times=RETRY_ATTEMPTS,
    )

    process(manager)

    result = stored_result(deletions_store)
    assert result.reason is DeletionReason.DELETE_ERROR
    assert result.reason_detail == "rejected:illegal_argument_exception"
    assert result.deleted_count == 0


def test_the_backoff_grows_by_the_factor_and_stops_at_the_maximum(
    make_manager: Callable[..., DeletionManager],
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
    sleeps: list[float],
) -> None:
    search_index.behavior.inject(
        index_ops.DELETE,
        OpenSearchUnavailableError("http_503"),
        key=seven_targets.expired[0],
        times=None,
    )

    process(make_manager(delete_error_retry_attempts=5, retry_backoff_max_seconds=3.0))

    assert sleeps == [1.0, 2.0, 3.0, 3.0]  # 初回 1 秒、2 倍、上限 3 秒(4.4)
    assert stored_result(deletions_store).reason is DeletionReason.DELETE_ERROR


def test_the_jitter_is_applied_to_every_wait(
    deletion_config,
    results: DeletionResults,
    search_index: InMemorySearchIndex,
    jobs_reader,
    clock,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
    sleeps: list[float],
) -> None:
    search_index.behavior.inject(
        index_ops.DELETE,
        OpenSearchUnavailableError("http_503"),
        key=seven_targets.expired[0],
        times=RETRY_ATTEMPTS,
    )
    jittered = create_deletion_manager(
        deletion_config,
        results=results,
        search_index=search_index,
        jobs=jobs_reader,
        clock=clock,
        jitter=lambda delay: delay / 2,
        sleep=sleeps.append,
    )

    process(jittered)

    assert sleeps == [0.5, 1.0]


def test_a_stop_request_during_the_backoff_leaves_the_result_running(
    deletion_config,
    results: DeletionResults,
    search_index: InMemorySearchIndex,
    jobs_reader,
    clock,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    holder: list[DeletionManager] = []
    search_index.behavior.inject(
        index_ops.DELETE,
        OpenSearchUnavailableError("http_503"),
        key=seven_targets.expired[0],
        times=None,
    )
    stopping = create_deletion_manager(
        deletion_config,
        results=results,
        search_index=search_index,
        jobs=jobs_reader,
        clock=clock,
        sleep=lambda seconds: holder[0].stop(),  # 待っている間に停止が要請される
    )
    holder.append(stopping)

    outcome = process(stopping)

    assert outcome is DeletionOutcome.STOPPED
    assert (
        stored_result(deletions_store).status is DeletionStatus.RUNNING
    )  # 再起動時の整理で failed
    assert len(search_index.behavior.calls_of(index_ops.DELETE)) == 1  # 再試行に進まない


def test_a_stop_request_lets_the_running_batch_finish_but_not_the_next(
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    next_batch_first = seven_targets.expired[BATCH_SIZE]
    search_index.behavior.before(
        index_ops.FETCH_FOR_DELETION, manager.stop, key=seven_targets.expired[1]
    )

    outcome = process(manager)

    assert outcome is DeletionOutcome.STOPPED
    assert remaining(search_index, seven_targets.expired) == set(seven_targets.expired[BATCH_SIZE:])
    assert next_batch_first in remaining(search_index, seven_targets.expired)
    assert stored_result(deletions_store).status is DeletionStatus.RUNNING


# --- 自分の結果が終端状態・404 になった(D-41 の実行側、9.8) ---


def discard_directly(results: DeletionResults) -> Callable[[], None]:
    """別スレッドのソース削除による `discarded` の書き込みの再現(排他を取らずに書く)。"""

    def discard() -> None:
        current = results.fetch_result(CRAWL_ID)
        assert current is not None
        results.transition_to_terminal(
            current, DeletionStatus.DISCARDED, reason=DeletionReason.SOURCE_DELETED
        )

    return discard


def test_a_result_discarded_between_batches_stops_the_deletion_without_writing(
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    results: DeletionResults,
    seven_targets: Scenario,
) -> None:
    # 自分の結果の読み取りは、判定の前に 1 回、その後はバッチごとに 1 回。
    # 3 回目(2 バッチ目の前)の直前に破棄する。
    for _ in range(2):
        deletions_store.behavior.before(store_ops.FETCH, lambda: None, key=RESULT_ID)
    deletions_store.behavior.before(store_ops.FETCH, discard_directly(results), key=RESULT_ID)

    outcome = process(manager)

    result = stored_result(deletions_store)
    assert outcome is DeletionOutcome.CLOSED
    assert (result.status, result.reason) == (
        DeletionStatus.DISCARDED,
        DeletionReason.SOURCE_DELETED,
    )
    assert remaining(search_index, seven_targets.expired) == set(seven_targets.expired[BATCH_SIZE:])


def test_a_result_that_disappears_stops_the_deletion_and_is_not_recreated(
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    for _ in range(2):
        deletions_store.behavior.before(store_ops.FETCH, lambda: None, key=RESULT_ID)
    deletions_store.behavior.before(
        store_ops.FETCH, lambda: deletions_store.delete(RESULT_ID), key=RESULT_ID
    )

    outcome = process(manager)

    assert outcome is DeletionOutcome.CLOSED
    assert deletions_store.body_of(RESULT_ID) is None
    assert len(remaining(search_index, seven_targets.expired)) == 4


def test_a_terminal_write_that_loses_to_a_discard_does_not_overwrite_it(  # D-41、9.8
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    results: DeletionResults,
    seven_targets: Scenario,
) -> None:
    """最後のバッチを終えたあと、`deleted` を書く直前に `discarded` が書かれた。"""
    for _ in range(4):  # started_at、バッチ 3 回の進捗
        deletions_store.behavior.before(store_ops.REPLACE, lambda: None, key=RESULT_ID)
    deletions_store.behavior.before(store_ops.REPLACE, discard_directly(results), key=RESULT_ID)

    outcome = process(manager)

    result = stored_result(deletions_store)
    assert outcome is DeletionOutcome.CLOSED
    assert (result.status, result.reason) == (
        DeletionStatus.DISCARDED,
        DeletionReason.SOURCE_DELETED,
    )
    assert result.deleted_count == 6  # 最後のバッチ前の進捗のまま。`deleted`(7)は書かれない


# --- 書き込みの 409(R8) ---


def test_a_conflict_on_the_progress_write_is_reread_and_the_deletion_continues(
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    def another_writer_touches_the_result() -> None:
        stored = deletions_store.body_of(RESULT_ID)
        assert stored is not None
        deletions_store.seed(RESULT_ID, stored)  # 内容は同じで版だけが進む

    deletions_store.behavior.before(store_ops.REPLACE, lambda: None, key=RESULT_ID)
    deletions_store.behavior.before(
        store_ops.REPLACE, another_writer_touches_the_result, key=RESULT_ID
    )

    process(manager)

    assert stored_result(deletions_store).status is DeletionStatus.DELETED
    assert remaining(search_index, seven_targets.expired) == set()


def test_the_progress_write_after_a_conflict_is_actually_written(  # S4
    manager: DeletionManager,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    """読み直したあとの進捗の書き込みが、保存されている(終端状態の書き込みに頼らずに確認する)。"""
    stored_before_each_write: list[tuple[int | None, int | None]] = []

    def hook_for(call_number: int) -> Callable[[], None]:
        def record_stored_progress() -> None:
            stored = stored_result(deletions_store)
            stored_before_each_write.append((stored.deleted_count, stored.target_count))
            if call_number == 2:  # 1 バッチ目の進捗の書き込みの直前に、別の書き手が版を進める
                body = deletions_store.body_of(RESULT_ID)
                assert body is not None
                deletions_store.seed(RESULT_ID, body)

        return record_stored_progress

    # 書き込みは、`deletion_started_at`、1 バッチ目の進捗(409)とその書き直し、
    # 2・3 バッチ目の進捗、終端状態の 6 回。
    for call_number in range(1, 7):
        deletions_store.behavior.before(store_ops.REPLACE, hook_for(call_number), key=RESULT_ID)

    process(manager)

    # 4 回目の書き込みの前に、409 のあとの書き直し(3 回目)が (0, 7) を保存している。
    assert stored_before_each_write == [
        (None, None),
        (None, None),
        (None, None),
        (0, 7),
        (3, 7),
        (6, 7),
    ]


def test_conflicts_beyond_the_reread_limit_raise_and_leave_the_result_unchanged(
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    deletions_store.behavior.inject(store_ops.REPLACE, Conflict(), key=RESULT_ID, times=None)

    with pytest.raises(UnavailableError, match="write_conflict"):
        process(manager)

    assert stored_result(deletions_store).status is DeletionStatus.RUNNING
    assert len(deletions_store.behavior.calls_of(store_ops.REPLACE)) == 1 + MAX_REREADS
    assert search_index.write_calls() == []


def hold_the_terminal_write_in_conflict(
    deletions_store: InMemoryStore, *, writes_before: int
) -> None:
    """`writes_before` 回の書き込みのあとの書き込み(終端状態)を、上限を超えて 409 にする。"""
    for _ in range(writes_before):
        deletions_store.behavior.before(store_ops.REPLACE, lambda: None, key=RESULT_ID)
    deletions_store.behavior.before(
        store_ops.REPLACE,
        lambda: deletions_store.behavior.inject(
            store_ops.REPLACE, Conflict(), key=RESULT_ID, times=1 + MAX_REREADS
        ),
        key=RESULT_ID,
    )


def test_a_terminal_write_that_keeps_conflicting_raises_after_the_documents_are_deleted(  # S2
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    # 書き込みは、`deletion_started_at`、バッチ 3 回の進捗、そのあとが終端状態。
    hold_the_terminal_write_in_conflict(deletions_store, writes_before=4)

    with pytest.raises(UnavailableError, match="write_conflict"):
        process(manager)

    result = stored_result(deletions_store)
    assert result.status is DeletionStatus.RUNNING  # 終端状態は書かれていない
    assert result.deleted_count == 6  # 最後のバッチの前の進捗のまま
    assert remaining(search_index, seven_targets.expired) == set()  # 文書の削除は済んでいる
    assert len(deletions_store.behavior.calls_of(store_ops.REPLACE)) == 4 + 1 + MAX_REREADS


def test_a_rerun_after_the_failed_terminal_write_does_not_reduce_the_recorded_deleted_count(  # A2
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    hold_the_terminal_write_in_conflict(deletions_store, writes_before=4)
    with pytest.raises(UnavailableError):
        process(manager)

    outcome = process(manager)  # 次の走査での再実行。対象はもう残っていない

    result = stored_result(deletions_store)
    assert outcome is DeletionOutcome.FINISHED
    assert (result.status, result.target_count) == (DeletionStatus.DELETED, 0)
    assert result.deleted_count == 6  # 0 で上書きしない


def test_a_rerun_keeps_the_first_deletion_started_at(  # N2
    manager: DeletionManager,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    clock: FixedClock,
    seven_targets: Scenario,
) -> None:
    fail_the_maintenance_check_at(jobs_store, 3)  # 1 バッチ目のあとに障害
    with pytest.raises(OpenSearchUnavailableError):
        process(manager)
    assert stored_result(deletions_store).deletion_started_at == DEFAULT_NOW

    clock.advance(seconds=3_600)
    process(manager)

    result = stored_result(deletions_store)
    assert result.status is DeletionStatus.DELETED
    assert result.deletion_started_at == DEFAULT_NOW  # 再実行の時刻で書き直さない
    assert result.ended_at == DEFAULT_NOW + timedelta(seconds=3_600)


def test_a_rerun_after_a_partial_deletion_keeps_counting_from_the_recorded_deleted_count(  # A2
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    fail_the_maintenance_check_at(jobs_store, 4)  # 3 バッチ目の前に障害(進捗は 3 件と記録済み)
    with pytest.raises(OpenSearchUnavailableError):
        process(manager)
    interrupted = stored_result(deletions_store)
    assert interrupted.deleted_count == BATCH_SIZE
    assert remaining(search_index, seven_targets.expired) == {seven_targets.expired[-1]}

    outcome = process(manager)  # 残りの 1 件を削除する再実行

    result = stored_result(deletions_store)
    assert outcome is DeletionOutcome.FINISHED
    assert result.status is DeletionStatus.DELETED
    assert (result.target_count, result.deleted_count) == (1, BATCH_SIZE + 1)  # 3 から数え続ける
    assert remaining(search_index, seven_targets.expired) == set()


# --- メンテナンスフラグの確認の障害(I3(a)) ---


@pytest.mark.parametrize(
    ("nth_check", "deleted_batches"),
    [(1, 0), (2, 0), (3, 1)],
    ids=["before_judging", "before_the_first_batch", "before_the_second_batch"],
)
def test_a_failure_checking_the_maintenance_flag_never_means_the_flag_is_off(
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    seven_targets: Scenario,
    nth_check: int,
    deleted_batches: int,
) -> None:
    """フラグを読めないときは「立っていない」とみなして削除を進めず、異常として伝える。"""
    fail_the_maintenance_check_at(jobs_store, nth_check)

    with pytest.raises(OpenSearchUnavailableError):
        process(manager)

    assert stored_result(deletions_store).status is DeletionStatus.RUNNING
    deleted_count = deleted_batches * BATCH_SIZE
    assert remaining(search_index, seven_targets.expired) == set(
        seven_targets.expired[deleted_count:]
    )
    assert (
        len(search_index.write_calls()) == deleted_count
    )  # 文書の削除は、確認できたバッチの分だけ


def test_an_opensearch_failure_while_judging_leaves_the_result_running(
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    seven_targets: Scenario,
) -> None:
    search_index.behavior.inject(index_ops.REFRESH, OpenSearchUnavailableError("http_503"))

    with pytest.raises(OpenSearchUnavailableError):
        process(manager)

    result = stored_result(deletions_store)
    assert result.status is DeletionStatus.RUNNING
    assert result.deletion_started_at == DEFAULT_NOW  # 判定に入ったことは記録済み
    assert search_index.write_calls() == []
