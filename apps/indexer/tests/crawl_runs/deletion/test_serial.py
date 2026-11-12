"""同じソースの削除の直列処理と、各削除が自分の設定で動くこと(arch 9.7 順1、9.9)。

D-31・D-32・D-36・D-46・D-92 の待機の側を確認する。待機中は判定せず、何も書かない。
"""

from datetime import timedelta

import pytest

from loreley_indexer.crawl_runs import CrawlRuns, DeletionManager, DeletionOutcome
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionStatus,
    deletion_result_record_id,
)
from tests.crawl_runs.deletion.scenario import (
    EXPIRED_AT,
    OTHER_SOURCE_ID,
    SEEN_AT,
    SEEN_BASE,
    TTL_SECONDS,
    document_source,
    ids,
    process,
    queued_result,
    raise_the_maintenance_flag_at_check,
    received_at,
    remaining,
    seed_documents,
)
from tests.crawl_runs.factories import (
    CRAWL_STARTED_AT,
    SOURCE_ID,
    make_finish,
    make_generation,
    make_result,
    make_start,
    seed_result,
    snapshot,
    stored_result,
)
from tests.fakes.clock import DEFAULT_NOW
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore

A, B, C = "job-a", "job-b", "job-c"
NEWER = CRAWL_STARTED_AT + timedelta(days=1)


def seed_queue(search_index: InMemorySearchIndex, deletions_store: InMemoryStore) -> None:
    """同じソースで、A、B、C の順に終了通知を受理済み(3 世代が続く。D-32)。"""
    seed_documents(search_index, ids(SEEN_BASE, 3), last_seen_at=SEEN_AT)
    seed_documents(search_index, ids(2_000, 2), last_seen_at=EXPIRED_AT)
    for number, crawl_id in enumerate((A, B, C)):
        seed_result(
            deletions_store,
            queued_result(crawl_id, enumerated_count=3, finish_received_at=received_at(number)),
        )


def test_later_deletions_wait_for_the_preceding_ones_and_write_nothing(  # D-31、D-32、D-92(a)
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    seed_queue(search_index, deletions_store)
    before = snapshot(deletions_store)

    assert process(manager, B) is DeletionOutcome.WAITING
    assert process(manager, C) is DeletionOutcome.WAITING

    # 待機中は判定せず(検索インデックスを読まず)、削除結果にも何も書かない。
    assert snapshot(deletions_store) == before
    assert search_index.behavior.calls == []
    assert stored_result(deletions_store, B).deletion_started_at is None


def test_the_deletions_run_in_the_order_they_were_received(  # D-32
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    seed_queue(search_index, deletions_store)

    assert process(manager, A) is DeletionOutcome.FINISHED
    assert process(manager, C) is DeletionOutcome.WAITING  # B がまだ終端でない
    assert process(manager, B) is DeletionOutcome.FINISHED
    assert process(manager, C) is DeletionOutcome.FINISHED

    statuses = [stored_result(deletions_store, crawl_id).status for crawl_id in (A, B, C)]
    assert statuses == [DeletionStatus.DELETED] * 3


def test_a_following_deletion_proceeds_when_the_preceding_one_ended_as_failed(  # D-32、D-44
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    seed_queue(search_index, deletions_store)
    failed_a = stored_result(deletions_store, A)
    seed_result(
        deletions_store,
        make_result(
            crawl_id=A,
            status=DeletionStatus.FAILED,
            reason=DeletionReason.DELETE_ERROR,
            reason_detail="unavailable:http_503",
            finish_received_at=failed_a.finish_received_at,
            finish_request_digest="d" * 64,
            ended_at=DEFAULT_NOW,
        ),
    )

    assert process(manager, B) is DeletionOutcome.FINISHED


def test_with_the_same_receipt_time_the_smaller_crawl_id_goes_first(  # D-46(a)
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    seed_documents(search_index, ids(SEEN_BASE, 3), last_seen_at=SEEN_AT)
    for crawl_id in (B, A):
        seed_result(deletions_store, queued_result(crawl_id, enumerated_count=3))

    assert process(manager, B) is DeletionOutcome.WAITING
    assert process(manager, A) is DeletionOutcome.FINISHED
    assert process(manager, B) is DeletionOutcome.FINISHED


def test_a_running_result_without_a_finish_notification_is_not_waited_for(  # D-46(b)
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    seed_documents(search_index, ids(SEEN_BASE, 3), last_seen_at=SEEN_AT)
    seed_result(deletions_store, make_result(crawl_id=A))  # 終了通知が届いていない世代
    seed_result(deletions_store, queued_result(B, enumerated_count=3))

    assert process(manager, B) is DeletionOutcome.FINISHED
    assert stored_result(deletions_store, A).status is DeletionStatus.RUNNING  # 触れない


def test_a_deletion_of_another_source_does_not_make_this_one_wait(
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    seed_documents(search_index, ids(SEEN_BASE, 3), last_seen_at=SEEN_AT)
    seed_result(deletions_store, queued_result(A, enumerated_count=3, source_id=OTHER_SOURCE_ID))
    seed_result(
        deletions_store, queued_result(B, enumerated_count=3, finish_received_at=received_at(1))
    )

    assert process(manager, B) is DeletionOutcome.FINISHED


def test_a_result_without_a_finish_notification_is_not_queued(
    manager: DeletionManager, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result(crawl_id=A))

    assert process(manager, A) is DeletionOutcome.NOT_QUEUED
    assert deletions_store.write_calls() == []


def test_a_terminal_or_missing_result_is_closed_without_writing(
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result(crawl_id=A, status=DeletionStatus.DISCARDED))

    assert process(manager, A) is DeletionOutcome.CLOSED
    assert process(manager, "unknown") is DeletionOutcome.CLOSED
    assert deletions_store.write_calls() == []
    assert search_index.behavior.calls == []


def test_the_flag_stops_the_running_deletion_and_fails_the_waiting_one_without_judging(  # D-33
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
) -> None:
    seed_documents(search_index, ids(SEEN_BASE, 3), last_seen_at=SEEN_AT)
    expired = ids(2_000, 7)
    seed_documents(search_index, expired, last_seen_at=EXPIRED_AT)
    for number, crawl_id in enumerate((A, B)):
        seed_result(
            deletions_store,
            queued_result(
                crawl_id,
                enumerated_count=3,
                finish_received_at=received_at(number),
                min_delete_count=100,
            ),
        )
    # A の 1 バッチ目の前の確認は通り、2 バッチ目の前の確認(全体で 3 回目)でフラグが立っている。
    raise_the_maintenance_flag_at_check(jobs_store, 3)

    process(manager, A)
    calls_after_a = len(search_index.behavior.calls)
    process(manager, B)

    result_a, result_b = (stored_result(deletions_store, crawl_id) for crawl_id in (A, B))
    assert (result_a.status, result_a.reason) == (DeletionStatus.FAILED, DeletionReason.MAINTENANCE)
    assert result_a.deleted_count == 3  # 実行済みのバッチの分は削除済み、未実行の分は削除されない
    assert (result_b.status, result_b.reason) == (DeletionStatus.FAILED, DeletionReason.MAINTENANCE)
    assert result_b.deletion_started_at is None  # 判定に進んでいない
    assert len(search_index.behavior.calls) == calls_after_a  # 検索インデックスを読んでいない
    assert len(set(search_index.document_ids()) & set(expired)) == 4


# --- 各削除は、自分の設定スナップショット(複写した値)で動く(D-36) ---


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        # (a) 旧い削除は強制削除モード(割合ルールを無視)、新しい削除は割合ルールを適用する。
        (
            {"forced": True},
            {"forced": False},
            (DeletionStatus.DELETED, DeletionStatus.SKIPPED_BY_RATIO),
        ),
        # (b) 旧い削除は割合ルールを適用し、新しい削除だけが強制削除モードになる。
        (
            {"forced": False},
            {"forced": True},
            (DeletionStatus.SKIPPED_BY_RATIO, DeletionStatus.DELETED),
        ),
        # しきい値も、それぞれの値で判定される。
        (
            {"ratio_threshold": 1.0},
            {"ratio_threshold": 0.0},
            (DeletionStatus.DELETED, DeletionStatus.SKIPPED_BY_RATIO),
        ),
    ],
    ids=["old_forced", "new_forced", "old_loose_threshold"],
)
def test_each_deletion_uses_its_own_copied_settings(  # D-36
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    first: dict[str, object],
    second: dict[str, object],
    expected: tuple[DeletionStatus, DeletionStatus],
) -> None:
    common = {"min_delete_count": 0, "ratio_threshold": 0.2, "forced": False}
    # `deletion-{source_id}`(最新の開始通知の内容)は、判定に使われない。逆の値を置いておく。
    deletions_store.seed(
        f"deletion-{SOURCE_ID}",
        make_generation(
            force_delete=not second.get("forced", False), ratio_threshold=0.9
        ).to_body(),
    )
    # 最初の削除が対象の文書を消さないよう、A は 20 件すべてが対象で、割合 100% になる。
    seed_documents(search_index, ids(2_000, 20), last_seen_at=EXPIRED_AT)
    seed_result(deletions_store, queued_result(A, enumerated_count=0, **{**common, **first}))
    seed_result(
        deletions_store,
        queued_result(
            B, enumerated_count=0, finish_received_at=received_at(1), **{**common, **second}
        ),
    )

    process(manager, A)
    # 最初が `deleted` なら対象の文書はもうない。B の割合を確かめられるよう、文書を戻す。
    seed_documents(search_index, ids(2_000, 20), last_seen_at=EXPIRED_AT)
    process(manager, B)

    results = (stored_result(deletions_store, A), stored_result(deletions_store, B))
    assert tuple(result.status for result in results) == expected
    assert results[0].forced is first.get("forced", False)
    assert results[1].forced is second.get("forced", False)


def test_the_ttl_of_each_result_decides_its_targets(  # D-36(TTL も複写した値)
    manager: DeletionManager, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    documents = ids(2_000, 3)
    seed_documents(search_index, documents, last_seen_at=EXPIRED_AT)  # 5 日前
    seed_result(deletions_store, queued_result(A, enumerated_count=0, ttl=30 * 86_400))
    seed_result(
        deletions_store, queued_result(B, enumerated_count=0, finish_received_at=received_at(1))
    )  # B の TTL は 3 日(`queued_result` の既定)

    process(manager, A)

    # A の 30 日の TTL では、5 日前に見つかった文書は期限切れにならない。
    result_a = stored_result(deletions_store, A)
    assert (result_a.status, result_a.target_count, result_a.deleted_count) == (
        DeletionStatus.DELETED,
        0,
        0,
    )
    assert remaining(search_index, documents) == set(documents)

    process(manager, B)

    # B の 3 日の TTL では、同じ文書が期限切れで、対象になる。
    result_b = stored_result(deletions_store, B)
    assert (result_b.status, result_b.target_count, result_b.deleted_count) == (
        DeletionStatus.DELETED,
        3,
        3,
    )
    assert remaining(search_index, documents) == set()


def test_a_deletion_skipped_by_the_ratio_is_not_carried_over_to_the_next_crawl(  # D-4
    crawl_runs: CrawlRuns,
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
) -> None:
    seen, expired = ids(SEEN_BASE, 5), ids(2_000, 5)
    seed_documents(search_index, seen, last_seen_at=SEEN_AT)
    seed_documents(search_index, expired, last_seen_at=EXPIRED_AT)
    crawl_runs.start_crawl(make_start(crawl_id=A, ttl=TTL_SECONDS, min_delete_count=0))
    crawl_runs.finish_crawl(
        make_finish(
            crawl_id=A,
            enumerated_count=5,
            skipped_document_ids=(),
            oversize_document_ids=(),
        )
    )
    manager.worker.run_once()
    first = stored_result(deletions_store, A)
    assert (first.status, first.target_count, first.denominator) == (
        DeletionStatus.SKIPPED_BY_RATIO,
        5,
        10,
    )
    first_record = deletions_store.body_of(deletion_result_record_id(A))

    # 次のクロールは、前回の 5 件と、期限切れだった 3 件を見つけた(対象は 2 件、率は 2/10)。
    refound, still_expired = expired[:3], expired[3:]
    for document_id in (*seen, *refound):
        search_index.seed(document_id, document_source(SOURCE_ID, NEWER))
    crawl_runs.start_crawl(
        make_start(crawl_id=B, crawl_started_at=NEWER, ttl=TTL_SECONDS, min_delete_count=0)
    )
    crawl_runs.finish_crawl(
        make_finish(
            crawl_id=B,
            enumerated_count=5 + 3,
            skipped_document_ids=(),
            oversize_document_ids=(),
        )
    )
    manager.worker.run_once()

    second = stored_result(deletions_store, B)
    # 前回の見送りを引き継がず、B 自身の件数・設定で新しく判定される。
    assert second.status is DeletionStatus.DELETED
    assert (second.n_seen, second.target_count, second.denominator, second.deleted_count) == (
        8,
        2,
        10,
        2,
    )
    assert remaining(search_index, still_expired) == set()
    assert remaining(search_index, refound) == set(refound)
    # 前回の結果は履歴として残り、変わらない。
    assert deletions_store.body_of(deletion_result_record_id(A)) == first_record
