"""新しいクロールが始まっても、受理済みの旧い削除は止まらない(arch 9.9、9.12)。

開始・終了通知(`CrawlRuns`)と削除(`DeletionManager`)を組み合わせて、
D-12・D-31・D-39・D-92(a)(b)・D-93 を確認する。削除バッチは実行ゲート(`Gate`)で止める。
"""

from datetime import timedelta

import pytest

from loreley_indexer.common.errors import FinishContentMismatchError
from loreley_indexer.crawl_runs import CrawlRuns, DeletionManager, DeletionOutcome
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionStatus,
    deletion_record_id,
)
from tests.crawl_runs.deletion.scenario import (
    EXPIRED_AT,
    NEW_BASE,
    SEEN_AT,
    SEEN_BASE,
    TTL_SECONDS,
    ids,
    remaining,
    seed_documents,
)
from tests.crawl_runs.factories import (
    CRAWL_ID,
    CRAWL_STARTED_AT,
    SOURCE_ID,
    make_finish,
    make_start,
    stored_generation,
    stored_result,
)
from tests.documents.factories import source_of
from tests.fakes import in_memory_search_index as index_ops
from tests.fakes.concurrency import Background
from tests.fakes.gate import Gate
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore

NEWER = CRAWL_STARTED_AT + timedelta(days=1)
NEWER_TEXT = "2026-11-10T01:00:00.000Z"
NEW_CRAWL = "job-new"
FINISH_SAME_AS_FIRST = {
    "enumerated_count": 3,
    "skipped_document_ids": (),
    "oversize_document_ids": (),
}


def start_and_finish(crawl_runs: CrawlRuns, crawl_id: str = CRAWL_ID, **finish: object) -> None:
    crawl_runs.start_crawl(make_start(crawl_id=crawl_id, ttl=TTL_SECONDS))
    crawl_runs.finish_crawl(
        make_finish(
            crawl_id=crawl_id,
            enumerated_count=3,
            skipped_document_ids=(),
            oversize_document_ids=(),
            **finish,
        )
    )


def test_a_new_start_notification_during_a_batch_does_not_stop_the_old_deletion(  # D-12、D-39
    crawl_runs: CrawlRuns,
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
) -> None:
    seen = ids(SEEN_BASE, 3)
    expired = ids(2_000, 7)
    seed_documents(search_index, seen, last_seen_at=SEEN_AT)
    seed_documents(search_index, expired, last_seen_at=EXPIRED_AT)
    start_and_finish(crawl_runs)
    updated_by_the_new_crawl = expired[5]  # 2 バッチ目に入る文書を、新しいクロールが更新する

    def new_crawl_arrives_during_the_first_batch() -> None:
        crawl_runs.start_crawl(
            make_start(crawl_id=NEW_CRAWL, crawl_started_at=NEWER, ttl=TTL_SECONDS)
        )
        search_index.seed(
            updated_by_the_new_crawl, {"source_id": SOURCE_ID, "last_seen_at": NEWER_TEXT}
        )
        crawl_runs.finish_crawl(make_finish(crawl_id=CRAWL_ID, **FINISH_SAME_AS_FIRST))  # D-39(c)
        with pytest.raises(FinishContentMismatchError):  # D-91(b)
            crawl_runs.finish_crawl(make_finish(crawl_id=CRAWL_ID, enumerated_count=99))

    search_index.behavior.before(index_ops.DELETE, new_crawl_arrives_during_the_first_batch)

    assert manager.worker.run_once() is True

    old = stored_result(deletions_store, CRAWL_ID)
    assert old.status is DeletionStatus.DELETED  # `discarded` にならず、終端まで走る
    assert (old.target_count, old.deleted_count) == (7, 6)
    # その間に新しいクロールが更新した文書は、TTL の再確認で消えない。
    assert remaining(search_index, expired) == {updated_by_the_new_crawl}
    assert remaining(search_index, seen) == set(seen)
    new = stored_result(deletions_store, NEW_CRAWL)
    assert new.status is DeletionStatus.RUNNING  # 新しい結果は即時に受理され、止められていない
    assert stored_generation(deletions_store).crawl_id == NEW_CRAWL


def test_a_new_start_notification_before_the_first_batch_does_not_stop_it(  # D-12
    crawl_runs: CrawlRuns,
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
) -> None:
    seen, expired = ids(SEEN_BASE, 3), ids(2_000, 4)
    seed_documents(search_index, seen, last_seen_at=SEEN_AT)
    seed_documents(search_index, expired, last_seen_at=EXPIRED_AT)
    start_and_finish(crawl_runs)
    crawl_runs.start_crawl(make_start(crawl_id=NEW_CRAWL, crawl_started_at=NEWER, ttl=TTL_SECONDS))

    manager.worker.run_once()

    assert stored_result(deletions_store, CRAWL_ID).status is DeletionStatus.DELETED
    assert remaining(search_index, expired) == set()


def test_a_following_deletion_waits_with_its_own_id_lists_until_the_running_one_ends(  # D-31、D-92
    crawl_runs: CrawlRuns,
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
) -> None:
    """A の実行中(バッチの途中)に B の終了通知を受理し、続けて C の開始通知が届く。

    B は待機中(`running`)のまま、自分の ID 一覧を保持する(A のものと混ざらない)。A が終端に
    なると、B は自分の ID 一覧で件数照合して判定に進む。
    """
    existing = ids(SEEN_BASE, 5)  # 列挙で見つかった文書(うち 2 件は B ではスキップ)
    expired = ids(2_000, 7)
    seed_documents(search_index, existing, last_seen_at=SEEN_AT)
    seed_documents(search_index, expired, last_seen_at=EXPIRED_AT)
    crawl_runs.start_crawl(make_start(ttl=TTL_SECONDS, min_delete_count=100))
    crawl_runs.finish_crawl(
        make_finish(enumerated_count=5, skipped_document_ids=existing[:2], oversize_document_ids=())
    )
    gate = Gate()
    search_index.behavior.before(index_ops.DELETE, gate.pass_through, key=expired[0])
    running = Background(manager.worker.run_once)
    gate.wait_until_arrived()  # A の最初のバッチの途中

    # B: 新しいクロールが文書を見つけ直し(`last_seen_at` を更新)、終了通知を送る。
    for document_id in existing:
        search_index.seed(document_id, {"source_id": SOURCE_ID, "last_seen_at": NEWER_TEXT})
    new_skipped = ids(NEW_BASE, 1)
    new_oversize = ids(NEW_BASE + 100, 1)
    crawl_runs.start_crawl(
        make_start(crawl_id="job-b", crawl_started_at=NEWER, ttl=TTL_SECONDS, min_delete_count=100)
    )
    crawl_runs.finish_crawl(  # 受理は、実行中のバッチを待たずに済む
        make_finish(
            crawl_id="job-b",
            enumerated_count=5 + 2,  # N_seen(5。既存のスキップ 2 件を含む)+ E_missing(2)
            skipped_document_ids=(*existing[:2], *new_skipped),
            oversize_document_ids=new_oversize,
        )
    )
    crawl_runs.start_crawl(  # C の開始通知で世代が進む
        make_start(crawl_id="job-c", crawl_started_at=NEWER + timedelta(hours=1), ttl=TTL_SECONDS)
    )

    b_while_a_runs = stored_result(deletions_store, "job-b")
    status_of_b = crawl_runs.crawl_status("job-b")
    assert b_while_a_runs.status is DeletionStatus.RUNNING
    assert b_while_a_runs.skipped_document_ids == tuple(sorted((*existing[:2], *new_skipped)))
    assert b_while_a_runs.oversize_document_ids == new_oversize
    assert (status_of_b.status, status_of_b.waiting_for) == (
        DeletionStatus.RUNNING,
        CRAWL_ID,
    )  # D-31
    assert manager.processor.process("job-b") is DeletionOutcome.WAITING  # 判定せず、何も書かない
    assert stored_result(deletions_store, "job-b") == b_while_a_runs
    assert stored_generation(deletions_store).crawl_id == "job-c"

    gate.release()
    running.join()
    assert stored_result(deletions_store, CRAWL_ID).status is DeletionStatus.DELETED

    assert manager.worker.run_once() is True  # B の順番
    result_b = stored_result(deletions_store, "job-b")
    # A のもの(`e_missing` 0)で数えていれば、5 + 0 ≠ 7 で `validation_failed` になる。
    assert result_b.status is DeletionStatus.DELETED
    assert (result_b.n_seen, result_b.e_missing) == (5, 2)
    assert remaining(search_index, existing) == set(existing)  # スキップ文書は削除されない
    assert result_b.skipped_document_ids is None  # 終端状態へ遷移する書き込みで消える(K35)
    assert result_b.finish_request_digest is not None  # ダイジェストは残る
    assert deletion_record_id(SOURCE_ID) in deletions_store.record_ids()
    assert source_of(search_index, existing[0])["last_seen_at"] == NEWER_TEXT


def test_the_oldest_deletion_runs_first_when_both_were_received_before_the_worker_ran(  # D-32
    crawl_runs: CrawlRuns,
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
) -> None:
    seed_documents(search_index, ids(SEEN_BASE, 3), last_seen_at=SEEN_AT)
    start_and_finish(crawl_runs, "job-a")
    crawl_runs.start_crawl(make_start(crawl_id="job-b", crawl_started_at=NEWER, ttl=TTL_SECONDS))
    for document_id in ids(SEEN_BASE, 3):
        search_index.seed(document_id, {"source_id": SOURCE_ID, "last_seen_at": NEWER_TEXT})
    crawl_runs.finish_crawl(
        make_finish(
            crawl_id="job-b",
            enumerated_count=3,
            skipped_document_ids=(),
            oversize_document_ids=(),
        )
    )
    assert crawl_runs.crawl_status("job-b").waiting_for == "job-a"

    manager.worker.run_once()

    assert stored_result(deletions_store, "job-a").status is DeletionStatus.DELETED
    assert stored_result(deletions_store, "job-b").status is DeletionStatus.RUNNING
    manager.worker.run_once()
    assert stored_result(deletions_store, "job-b").status is DeletionStatus.DELETED


def test_after_a_restart_neither_of_two_waiting_deletions_is_resumed(  # D-93(再起動側)
    crawl_runs: CrawlRuns,
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
) -> None:
    """待機中の 2 件(どちらも未処理)が、再起動の整理で `failed` になり、再開されない。

    A が実行中の構成(進捗が記録済み)は `test_restart.py` が確認する。
    """
    expired = ids(2_000, 4)
    seed_documents(search_index, ids(SEEN_BASE, 3), last_seen_at=SEEN_AT)
    seed_documents(search_index, expired, last_seen_at=EXPIRED_AT)
    start_and_finish(crawl_runs, "job-a")
    crawl_runs.start_crawl(make_start(crawl_id="job-b", crawl_started_at=NEWER, ttl=TTL_SECONDS))
    crawl_runs.finish_crawl(
        make_finish(
            crawl_id="job-b",
            enumerated_count=3,
            skipped_document_ids=(),
            oversize_document_ids=(),
        )
    )

    failed_count = crawl_runs.fail_unfinished_crawls_after_restart()  # 起動時の整理(ワーカーより先)
    progressed = manager.worker.run_once()

    assert failed_count == 2
    assert progressed is False
    for crawl_id in ("job-a", "job-b"):
        result = stored_result(deletions_store, crawl_id)
        assert (result.status, result.reason) == (
            DeletionStatus.FAILED,
            DeletionReason.INDEXER_RESTART,
        )
        assert result.deleted_count == 0  # 設計書 D-93: 削除は 0 件
    assert search_index.write_calls() == []  # 削除は 1 件も実行されない
    assert remaining(search_index, expired) == set(expired)
