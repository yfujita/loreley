"""削除の判定(arch 9.7 の順2〜5、9.3、9.6)。

D-1〜D-6・D-10・D-13・D-21・D-25・D-38・D-72・D-76(a)・D-85・D-92(b)(c)の判定側、
E-1・E-8・E-9・E-10・E-27・E-41 を確認する。
「削除されてはならない文書が消えない」ことを、各ケースで文書の残りで確かめる。
"""

import logging
import math
from datetime import timedelta

import pytest

from loreley_indexer.common.errors import UnavailableError
from loreley_indexer.crawl_runs import DeletionManager, DeletionOutcome
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionStatus,
    MalformedRecordError,
    deletion_result_record_id,
)
from loreley_indexer.infrastructure.opensearch import Conflict
from tests.crawl_runs.deletion.conftest import MAX_REREADS
from tests.crawl_runs.deletion.scenario import (
    EXPIRED_AT,
    NEW_BASE,
    SEEN_AT,
    SEEN_BASE,
    STALE_BASE,
    Scenario,
    ids,
    process,
    queued_result,
    remaining,
    seed_documents,
    seed_scenario,
)
from tests.crawl_runs.factories import CRAWL_ID, seed_result, stored_result
from tests.documents.factories import (
    MALFORMED_MAINTENANCE_BODIES,
    set_maintenance,
    set_malformed_maintenance,
)
from tests.fakes import in_memory_search_index as index_ops
from tests.fakes import in_memory_store as store_ops
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore

SENTINEL = "sentinel-record-value"


def assert_nothing_deleted(search_index: InMemorySearchIndex, scenario: Scenario) -> None:
    assert search_index.write_calls() == []
    everything = scenario.seen + scenario.expired + scenario.within_ttl + scenario.others
    assert remaining(search_index, everything) == set(everything)


# --- 割合ルール(D-1〜D-3、D-25、E-1、E-27) ---


def test_a_target_within_the_ratio_is_deleted_and_the_numbers_are_recorded(  # D-3
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=18, expired=2, min_delete_count=0)

    outcome = process(manager)

    result = stored_result(deletions_store)
    assert outcome is DeletionOutcome.FINISHED
    assert result.status is DeletionStatus.DELETED
    assert result.reason is None
    assert (result.n_seen, result.e_missing) == (18, 0)
    assert (result.target_count, result.denominator, result.deleted_count) == (2, 20, 2)
    assert result.enumerated_count == 18
    assert (result.deletion_started_at, result.ended_at) == (DEFAULT_NOW, DEFAULT_NOW)
    assert remaining(search_index, scenario.expired) == set()
    assert remaining(search_index, scenario.seen) == set(scenario.seen)


def test_a_target_over_the_ratio_is_not_deleted_and_is_recorded_as_skipped(  # D-1
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=5, expired=5, min_delete_count=0)

    process(manager)

    result = stored_result(deletions_store)
    assert result.status is DeletionStatus.SKIPPED_BY_RATIO
    assert (result.target_count, result.denominator) == (5, 10)
    assert result.deleted_count is None
    assert_nothing_deleted(search_index, scenario)


def test_the_ratio_exactly_at_the_threshold_is_deleted(
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    seed_scenario(search_index, deletions_store, seen=8, expired=2, min_delete_count=0)

    process(manager)

    assert stored_result(deletions_store).status is DeletionStatus.DELETED  # 2/10 == 0.2


def test_a_target_at_the_minimum_count_is_deleted_whatever_the_ratio(  # D-2
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=0, expired=10, min_delete_count=10)

    process(manager)

    assert stored_result(deletions_store).status is DeletionStatus.DELETED
    assert remaining(search_index, scenario.expired) == set()


def test_one_target_above_the_minimum_count_is_judged_by_the_ratio(  # D-2 の境界
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=0, expired=11, min_delete_count=10)

    process(manager)

    assert stored_result(deletions_store).status is DeletionStatus.SKIPPED_BY_RATIO
    assert_nothing_deleted(search_index, scenario)


def test_an_empty_listing_does_not_delete_everything_for_a_large_source(  # E-1、D-25
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=0, expired=20)

    process(manager)

    result = stored_result(deletions_store)
    assert result.status is DeletionStatus.SKIPPED_BY_RATIO
    assert (result.target_count, result.denominator) == (20, 20)
    assert_nothing_deleted(search_index, scenario)


def test_an_empty_listing_deletes_everything_for_a_small_source(  # E-27(既知の制限)
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=0, expired=5)

    process(manager)

    assert stored_result(deletions_store).status is DeletionStatus.DELETED
    assert remaining(search_index, scenario.expired) == set()


def test_documents_within_the_ttl_are_never_targets_even_when_not_seen(  # E-1(TTL 内)
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    scenario = seed_scenario(
        search_index, deletions_store, seen=2, within_ttl=3, enumerated_count=2
    )

    process(manager)

    result = stored_result(deletions_store)
    assert (result.status, result.target_count, result.denominator) == (
        DeletionStatus.DELETED,
        0,
        5,
    )
    assert_nothing_deleted(search_index, scenario)


def test_documents_of_other_sources_are_not_counted_in_the_denominator(  # I1(a)
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    """別ソースの文書が D に混ざると、割合が薄まって削除してしまう(5/10 が 5/110 になる)。"""
    scenario = seed_scenario(
        search_index,
        deletions_store,
        seen=5,
        expired=5,
        other_source_expired=100,
        min_delete_count=0,
    )

    process(manager)

    result = stored_result(deletions_store)
    assert result.status is DeletionStatus.SKIPPED_BY_RATIO
    assert (result.target_count, result.denominator) == (5, 10)
    assert search_index.write_calls() == []
    assert_nothing_deleted(search_index, scenario)


def test_documents_of_other_sources_are_not_counted_in_n_seen(  # I1(b)
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    """別ソースの文書が `N_seen` に混ざると、件数照合が合わず(または偶然合って)判定を誤る。"""
    scenario = seed_scenario(search_index, deletions_store, seen=3, other_source_seen=4)

    process(manager)

    result = stored_result(deletions_store)
    assert result.status is DeletionStatus.DELETED  # enumerated_count(3)と N_seen が一致する
    assert (result.n_seen, result.target_count, result.denominator) == (3, 0, 3)
    assert_nothing_deleted(search_index, scenario)


# --- 強制削除モード(D-5、D-6、E-9、E-10) ---


def test_forced_mode_ignores_the_ratio_and_the_minimum_count(  # D-5、E-9
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=0, expired=20, forced=True)

    process(manager)

    result = stored_result(deletions_store)
    assert (result.status, result.forced, result.deleted_count) == (
        DeletionStatus.DELETED,
        True,
        20,
    )
    assert remaining(search_index, scenario.expired) == set()


def test_forced_mode_deletes_only_expired_documents(  # E-10
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    scenario = seed_scenario(
        search_index,
        deletions_store,
        seen=5,
        within_ttl=3,
        expired=20,
        other_source_expired=4,
        forced=True,
    )

    process(manager)

    assert stored_result(deletions_store).deleted_count == 20
    assert remaining(search_index, scenario.expired) == set()
    assert remaining(search_index, scenario.seen) == set(scenario.seen)
    assert remaining(search_index, scenario.within_ttl) == set(scenario.within_ttl)
    assert remaining(search_index, scenario.others) == set(scenario.others)


def test_forced_mode_does_not_bypass_the_count_check(  # D-6
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    scenario = seed_scenario(
        search_index, deletions_store, seen=5, expired=20, forced=True, enumerated_count=6
    )

    process(manager)

    result = stored_result(deletions_store)
    assert (result.status, result.reason) == (
        DeletionStatus.VALIDATION_FAILED,
        DeletionReason.COUNT_MISMATCH,
    )
    assert_nothing_deleted(search_index, scenario)


def test_the_maintenance_flag_fails_the_deletion_before_it_judges(  # D-19、9.7 順2
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=3, expired=3)
    set_maintenance(jobs_store, enabled=True)

    outcome = process(manager)

    result = stored_result(deletions_store)
    assert outcome is DeletionOutcome.FINISHED
    assert (result.status, result.reason) == (DeletionStatus.FAILED, DeletionReason.MAINTENANCE)
    assert result.deletion_started_at is None  # 判定に進んでいない
    assert result.skipped_document_ids is None  # 終端状態へ遷移する書き込みで消える(K35)
    assert search_index.behavior.calls == []
    assert_nothing_deleted(search_index, scenario)


@pytest.mark.parametrize("body", MALFORMED_MAINTENANCE_BODIES)
def test_a_malformed_maintenance_flag_fails_the_deletion_like_an_enabled_one(  # fail-closed(0014)
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    body: dict[str, object],
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=3, expired=3)
    set_malformed_maintenance(jobs_store, body)

    outcome = process(manager)

    result = stored_result(deletions_store)
    assert outcome is DeletionOutcome.FINISHED
    assert (result.status, result.reason) == (DeletionStatus.FAILED, DeletionReason.MAINTENANCE)
    assert result.deletion_started_at is None
    assert_nothing_deleted(search_index, scenario)


def test_a_cleared_flag_does_not_stop_the_deletion(
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
) -> None:
    seed_scenario(search_index, deletions_store, seen=3, expired=3)
    set_maintenance(jobs_store, enabled=False)

    process(manager)

    assert stored_result(deletions_store).status is DeletionStatus.DELETED


def test_forced_mode_does_not_bypass_the_maintenance_flag(  # D-6
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=0, expired=20, forced=True)
    set_maintenance(jobs_store, enabled=True)

    process(manager)

    result = stored_result(deletions_store)
    assert (result.status, result.reason) == (DeletionStatus.FAILED, DeletionReason.MAINTENANCE)
    assert_nothing_deleted(search_index, scenario)


def test_forced_mode_does_not_delete_skipped_documents(  # D-6、二重防御
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    stale = ids(STALE_BASE, 2)
    seed_documents(search_index, stale, last_seen_at=EXPIRED_AT)
    scenario = seed_scenario(
        search_index, deletions_store, seen=0, expired=3, forced=True, skipped=stale
    )

    process(manager)

    assert remaining(search_index, scenario.expired) == set()
    assert remaining(search_index, stale) == set(stale)


# --- 件数照合と ID 一覧(D-13、D-21、D-38、D-92、E-41) ---


def test_a_count_mismatch_deletes_nothing_and_records_the_numbers(  # D-13
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=5, expired=3, enumerated_count=7)

    process(manager)

    result = stored_result(deletions_store)
    assert (result.status, result.reason) == (
        DeletionStatus.VALIDATION_FAILED,
        DeletionReason.COUNT_MISMATCH,
    )
    assert (result.enumerated_count, result.n_seen, result.e_missing) == (7, 5, 0)
    # ID 一覧は終端遷移の書き込みで消え、ダイジェストと受理の事実は残る(K35)。
    assert result.skipped_document_ids is None
    assert result.oversize_document_ids is None
    assert result.finish_request_digest == "d" * 64
    assert result.finish_received_at is not None
    assert result.target_count is None
    assert_nothing_deleted(search_index, scenario)


def test_skipped_and_oversize_documents_complete_the_count_and_are_not_deleted(  # D-21、E-41
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    existing_skipped = ids(SEEN_BASE, 2)  # 既存のスキップ文書は、列挙時の更新で N_seen に数えられる
    new_skipped = ids(NEW_BASE, 1)  # 新規のスキップ文書・サイズ超過文書は、E_missing に数える
    new_oversize = ids(NEW_BASE + 100, 1)
    scenario = seed_scenario(
        search_index,
        deletions_store,
        seen=5,
        expired=3,
        enumerated_count=5 + 2,
        skipped=(*existing_skipped, *new_skipped),
        oversize=new_oversize,
    )

    process(manager)

    result = stored_result(deletions_store)
    assert result.status is DeletionStatus.DELETED
    assert (result.n_seen, result.e_missing, result.target_count) == (5, 2, 3)
    assert remaining(search_index, scenario.expired) == set()
    assert remaining(search_index, existing_skipped) == set(existing_skipped)


def test_a_new_oversize_document_missing_from_the_lists_breaks_the_count(  # E-41
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    scenario = seed_scenario(
        search_index, deletions_store, seen=5, expired=3, enumerated_count=5 + 1
    )  # 列挙には新規のサイズ超過文書があるが、一覧にない

    process(manager)

    assert stored_result(deletions_store).reason is DeletionReason.COUNT_MISMATCH
    assert_nothing_deleted(search_index, scenario)


def test_an_id_in_both_lists_is_counted_once(  # 9.6(和集合)
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    both = ids(NEW_BASE, 1)
    seed_scenario(
        search_index,
        deletions_store,
        seen=2,
        expired=1,
        enumerated_count=2 + 1,
        skipped=both,
        oversize=both,
    )

    process(manager)

    result = stored_result(deletions_store)
    assert (result.status, result.e_missing) == (DeletionStatus.DELETED, 1)


def test_a_listed_document_is_never_a_target_even_if_its_last_seen_at_was_not_updated(  # D-10
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    """二重防御(9.2): `last_seen_at` の更新が漏れていても、スキップ・サイズ超過文書は消さない。"""
    stale_skipped = ids(STALE_BASE, 1)
    stale_oversize = ids(STALE_BASE + 1, 1)
    seed_documents(search_index, stale_skipped + stale_oversize, last_seen_at=EXPIRED_AT)
    scenario = seed_scenario(
        search_index,
        deletions_store,
        seen=4,
        expired=3,
        skipped=stale_skipped,
        oversize=stale_oversize,
    )

    process(manager)

    result = stored_result(deletions_store)
    assert (result.status, result.target_count) == (DeletionStatus.DELETED, 3)
    assert remaining(search_index, scenario.expired) == set()
    assert remaining(search_index, stale_skipped + stale_oversize) == set(
        stale_skipped + stale_oversize
    )


def test_extract_failed_documents_are_counted_in_n_seen_and_are_not_targets(  # D-27
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    """抽出に失敗した文書も、列挙で `last_seen_at` が更新されるので `N_seen` に数えられる。"""
    extract_failed = ids(NEW_BASE + 200, 2)
    seed_documents(
        search_index, extract_failed, last_seen_at=SEEN_AT, index_status="extract_failed"
    )
    scenario = seed_scenario(search_index, deletions_store, seen=3, expired=2, enumerated_count=5)

    process(manager)

    result = stored_result(deletions_store)
    assert result.status is DeletionStatus.DELETED  # 3 + 2 で件数照合が成立する
    assert (result.n_seen, result.target_count) == (5, 2)
    assert remaining(search_index, scenario.expired) == set()
    assert remaining(search_index, extract_failed) == set(extract_failed)


def test_an_update_by_a_newer_crawl_while_waiting_fails_the_count_and_deletes_nothing(  # D-38
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=5, expired=3)
    # 待機の間に、新しいクロールが別の文書を見つけて `last_seen_at` を更新した。
    search_index.seed(
        scenario.expired[0],
        {"source_id": scenario.result.source_id, "last_seen_at": "2026-11-10T00:00:00.000Z"},
    )

    process(manager)

    assert stored_result(deletions_store).reason is DeletionReason.COUNT_MISMATCH
    assert search_index.write_calls() == []


@pytest.mark.parametrize("forced", [False, True], ids=["ratio_rule", "forced"])
def test_an_over_limit_notification_is_judged_failed_without_touching_the_index(  # D-92(c)、K34
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    forced: bool,
) -> None:
    """強制削除モードでも、保存されていない ID 一覧のまま削除に進まない。"""
    stale = ids(STALE_BASE, 3)
    seed_documents(search_index, stale, last_seen_at=EXPIRED_AT)
    over_limit = queued_result(
        enumerated_count=0,
        skipped=None,
        oversize=None,
        skip_and_oversize_id_count=6,
        skip_and_oversize_id_limit_exceeded=True,
        forced=forced,
    )
    seed_result(deletions_store, over_limit)

    process(manager)

    result = stored_result(deletions_store)
    assert (result.status, result.reason) == (
        DeletionStatus.VALIDATION_FAILED,
        DeletionReason.ID_LIMIT_EXCEEDED,
    )
    assert result.skip_and_oversize_id_count == 6
    assert search_index.behavior.calls == []  # 判定でも検索インデックスを読まない
    assert remaining(search_index, stale) == set(stale)  # 実際に文書が残っている


@pytest.mark.parametrize(
    ("broken", "field_name"),
    [
        ({"skipped": None}, "skipped_document_ids"),
        ({"oversize": None}, "oversize_document_ids"),
        ({"enumerated_count": None}, "enumerated_count"),
    ],
    ids=["no_skipped_list", "no_oversize_list", "no_enumerated_count"],
)
def test_a_waiting_result_missing_its_lists_or_count_is_never_judged_and_deletes_nothing(  # I2
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    caplog: pytest.LogCaptureFixture,
    broken: dict[str, object],
    field_name: str,
) -> None:
    """保存した ID 一覧・件数がない記録は、空の一覧とみなして削除に進まない(フェイルクローズ)。

    保存した一覧が空だと「スキップ文書なし」と読めて、スキップ文書まで削除対象になりうる。
    """
    scenario = seed_scenario(
        search_index, deletions_store, seen=2, expired=3, finish_request_digest=SENTINEL, **broken
    )

    with pytest.raises(MalformedRecordError) as raised:
        process(manager)

    assert raised.value.field_name == field_name
    assert stored_result(deletions_store).status is DeletionStatus.RUNNING
    assert search_index.behavior.calls == []  # 検索インデックスを読んでも書いてもいない
    assert_nothing_deleted(search_index, scenario)

    with caplog.at_level(logging.DEBUG):
        assert manager.worker.run_once() is False  # ワーカーは落ちず、次の走査でも削除しない
    assert CRAWL_ID in caplog.text
    assert "MalformedRecordError" in caplog.text
    assert SENTINEL not in caplog.text  # 記録の値は出さない(R9)
    assert_nothing_deleted(search_index, scenario)


# --- D=0、T > D(D-72、D-85) ---


def test_zero_denominator_ends_as_deleted_without_dividing_or_reading_the_minimum_count(  # D-72
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    seed_result(
        deletions_store,
        queued_result(enumerated_count=0, min_delete_count=-5, ratio_threshold=math.nan),
    )

    process(manager)

    result = stored_result(deletions_store)
    assert result.status is DeletionStatus.DELETED
    assert (result.target_count, result.denominator, result.deleted_count) == (0, 0, 0)
    assert search_index.write_calls() == []


@pytest.mark.parametrize("forced", [False, True], ids=["ratio_rule", "forced"])
def test_a_target_count_above_the_denominator_is_a_validation_failure(  # D-85、U-33
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    forced: bool,
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=0, expired=3, forced=forced)

    def shrink_the_denominator() -> None:
        # 取り込みと D のカウントの間に、D が減った(別の削除など)。
        for document_id in scenario.expired:
            search_index.seed_removal(document_id)
        search_index.refresh()

    # 1 回目の `count`(`N_seen`)は通し、2 回目(D)の直前に差し込む。
    search_index.behavior.before(index_ops.COUNT, lambda: None)
    search_index.behavior.before(index_ops.COUNT, shrink_the_denominator)

    process(manager)

    result = stored_result(deletions_store)
    assert (result.status, result.reason) == (
        DeletionStatus.VALIDATION_FAILED,
        DeletionReason.TARGET_EXCEEDS_DENOMINATOR,
    )
    assert (result.target_count, result.denominator) == (3, 0)
    assert search_index.behavior.calls_of(index_ops.DELETE) == []


@pytest.mark.parametrize(
    ("removed_before_the_denominator", "expected_status"),
    [
        (0, DeletionStatus.DELETED),  # T == D: 分母は対象を含むので、通常の場合
        (1, DeletionStatus.VALIDATION_FAILED),  # T == D + 1: 対象のほうが多い
    ],
    ids=["target_equals_denominator", "target_exceeds_by_one"],
)
def test_the_target_guard_stops_only_when_the_target_exceeds_the_denominator(  # D-85 の境界、U-33
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    removed_before_the_denominator: int,
    expected_status: DeletionStatus,
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=0, expired=3, forced=True)

    def shrink_the_denominator() -> None:
        for document_id in scenario.expired[:removed_before_the_denominator]:
            search_index.seed_removal(document_id)
        search_index.refresh()

    # 1 回目の `count`(`N_seen`)は通し、2 回目(D)の直前に文書を減らす。
    search_index.behavior.before(index_ops.COUNT, lambda: None)
    search_index.behavior.before(index_ops.COUNT, shrink_the_denominator)

    process(manager)

    result = stored_result(deletions_store)
    assert result.status is expected_status
    assert result.target_count == 3
    assert result.denominator == 3 - removed_before_the_denominator


# --- スキップ文書と割合(D-10) ---


@pytest.mark.parametrize(
    ("ratio_threshold", "expected_status"),
    [
        (0.3, DeletionStatus.SKIPPED_BY_RATIO),  # D-10 の本旨: 除いた対象でも、割合が超える
        (0.4, DeletionStatus.DELETED),  # 割合の分子・分母の扱いを誤ると、ここで見送りに反転する
    ],
)
def test_the_ratio_uses_targets_without_the_skipped_documents_over_all_registered_documents(  # D-10
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    ratio_threshold: float,
    expected_status: DeletionStatus,
) -> None:
    """T = 4(スキップ文書 2 件を除く)、D = 11(登録済みのスキップ文書 2 件を含む)。

    T/D = 0.364。スキップ文書を T に含めると 6/11 = 0.545、D から除くと 4/9 = 0.444 で、
    どちらも 0.4 を超えて見送りになる。
    """
    skipped = ids(STALE_BASE, 2)
    seed_documents(search_index, skipped, last_seen_at=EXPIRED_AT)
    scenario = seed_scenario(
        search_index,
        deletions_store,
        seen=5,
        expired=4,
        min_delete_count=0,
        ratio_threshold=ratio_threshold,
        skipped=skipped,
    )

    process(manager)

    result = stored_result(deletions_store)
    assert result.status is expected_status
    assert (result.target_count, result.denominator) == (4, 11)
    assert remaining(search_index, skipped) == set(skipped)  # スキップ文書は、どちらでも消えない
    if expected_status is DeletionStatus.SKIPPED_BY_RATIO:
        assert_nothing_deleted(search_index, scenario)
        assert result.deleted_count is None
    else:
        assert remaining(search_index, scenario.expired) == set()


# --- 終端状態の書き込みの 409(判定側。S2) ---


def test_a_terminal_write_of_the_judgment_that_keeps_conflicting_raises_and_leaves_it_running(
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=5, expired=5, min_delete_count=0)
    result_id = deletion_result_record_id(CRAWL_ID)
    # 書き込みは、`deletion_started_at` のあとが終端状態(`skipped_by_ratio`)。
    deletions_store.behavior.before(store_ops.REPLACE, lambda: None, key=result_id)
    deletions_store.behavior.before(
        store_ops.REPLACE,
        lambda: deletions_store.behavior.inject(
            store_ops.REPLACE, Conflict(), key=result_id, times=1 + MAX_REREADS
        ),
        key=result_id,
    )

    with pytest.raises(UnavailableError, match="write_conflict"):
        process(manager)

    assert stored_result(deletions_store).status is DeletionStatus.RUNNING
    assert_nothing_deleted(search_index, scenario)


# --- 大きな対象、上限(D-76、K47) ---


def test_every_target_beyond_the_page_and_batch_sizes_is_deleted(  # D-76(a)
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    scenario = seed_scenario(
        search_index, deletions_store, seen=0, expired=10, min_delete_count=100
    )

    process(manager)

    result = stored_result(deletions_store)
    assert (result.target_count, result.deleted_count) == (10, 10)
    assert remaining(search_index, scenario.expired) == set()
    # ページサイズ 4 → 取り込みは 3 ページ、バッチサイズ 3 → 削除は 4 バッチ。
    assert len(search_index.behavior.calls_of(index_ops.SEARCH_IDS)) == 3


def test_too_many_targets_fail_the_deletion_with_nothing_deleted(
    make_manager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=0, expired=6, min_delete_count=100)

    process(make_manager(max_deletion_targets=5))

    result = stored_result(deletions_store)
    assert (result.status, result.reason) == (DeletionStatus.FAILED, DeletionReason.DELETE_ERROR)
    assert result.reason_detail == "target_limit_exceeded"
    assert result.deleted_count is None
    assert_nothing_deleted(search_index, scenario)


# --- 判定時刻の固定(9.8) ---


def test_the_cutoff_is_fixed_at_the_judgment_time(
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    clock: FixedClock,
) -> None:
    """`cutoff` は判定の先頭で 1 回決める。取り込みの直前に時計が進んでも、対象は変わらない。"""
    scenario = seed_scenario(search_index, deletions_store, seen=0, within_ttl=2)
    search_index.behavior.before(index_ops.SEARCH_IDS, lambda: clock.advance(seconds=10 * 86_400))

    process(manager)

    # 時計が進んだ後の時刻で `cutoff` を決めていれば、TTL 内の 2 件が対象になってしまう。
    result = stored_result(deletions_store)
    assert (result.status, result.target_count) == (DeletionStatus.DELETED, 0)
    assert_nothing_deleted(search_index, scenario)


def test_expiry_is_measured_from_the_judgment_time_not_from_the_crawl_start(  # S1、9.8
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    """期限は `判定時刻 - TTL`。`crawl_started_at` を基準にすると、この 2 件は期限内になる。"""
    scenario = seed_scenario(search_index, deletions_store, seen=3)
    # `SEEN_AT - 2.5日`: 判定時刻(`SEEN_AT` の約 1.96 日後)基準では TTL 3 日を超え、
    # `crawl_started_at`(= `SEEN_AT`)基準では TTL 内。
    between = ids(8_000, 2)
    seed_documents(search_index, between, last_seen_at=SEEN_AT - timedelta(days=2, hours=12))

    process(manager)

    result = stored_result(deletions_store)
    assert (result.status, result.target_count, result.deleted_count) == (
        DeletionStatus.DELETED,
        2,
        2,
    )
    assert remaining(search_index, between) == set()
    assert remaining(search_index, scenario.seen) == set(scenario.seen)
