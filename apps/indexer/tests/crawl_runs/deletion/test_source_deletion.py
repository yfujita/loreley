"""ソース削除 1〜3(arch 9.14、api 4.6〜4.8。案 8)。

D-35・D-41・D-42・D-74・D-84・D-90・E-43 を確認する。
ソース削除 2・3 はロックを確認し、不所有なら何も書かずに 409 `lock_not_owned`(案 8)。
"""

import pytest

from loreley_indexer.common.errors import LockNotOwnedError, UnavailableError
from loreley_indexer.common.locks import LockInfo
from loreley_indexer.crawl_runs import (
    DeletionConfig,
    DeletionManager,
    DeletionOutcome,
    create_deletion_manager,
)
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionResults,
    DeletionStatus,
    deletion_record_id,
    deletion_result_record_id,
)
from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    DeleteByQueryResult,
    DocumentFilter,
    OpenSearchUnavailableError,
    StoreJobsReader,
)
from tests.crawl_runs.deletion.conftest import BATCH_SIZE, DISCARD_ATTEMPTS, MAX_RERUNS
from tests.crawl_runs.deletion.scenario import (
    OTHER_SOURCE_ID,
    SEEN_AT,
    ids,
    queued_result,
    remaining,
    seed_documents,
    seed_scenario,
)
from tests.crawl_runs.factories import (
    CRAWL_ID,
    SOURCE_ID,
    make_generation,
    make_result,
    seed_result,
    snapshot,
    stored_result,
)
from tests.documents.factories import LOCK_OWNER, seed_lock
from tests.fakes import in_memory_search_index as index_ops
from tests.fakes import in_memory_store as store_ops
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.concurrency import Background
from tests.fakes.gate import Gate
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore

LOCK = LockInfo(owner=LOCK_OWNER, job_id="job-source-delete")
RESULT_ID = deletion_result_record_id(CRAWL_ID)


@pytest.fixture
def owned_lock(jobs_store: InMemoryStore) -> LockInfo:
    seed_lock(jobs_store, owner=LOCK.owner, job_id=LOCK.job_id)
    return LOCK


def seed_source_documents(
    search_index: InMemorySearchIndex, count: int, *, source_id: str = SOURCE_ID, base: int = 100
) -> tuple[str, ...]:
    document_ids = ids(base, count)
    seed_documents(search_index, document_ids, last_seen_at=SEEN_AT, source_id=source_id)
    return document_ids


# --- ソース削除 1: 削除結果の破棄(D-35) ---


def test_every_non_terminal_result_of_the_source_is_discarded_and_nothing_else(  # D-35
    manager: DeletionManager, deletions_store: InMemoryStore
) -> None:
    waiting = queued_result("job-waiting", enumerated_count=0)
    judging = queued_result("job-judging", enumerated_count=0, deletion_started_at=DEFAULT_NOW)
    executing = queued_result(
        "job-executing", enumerated_count=0, deletion_started_at=DEFAULT_NOW, deleted_count=4
    )
    no_finish = make_result(crawl_id="job-no-finish")
    finished = make_result(crawl_id="job-deleted", status=DeletionStatus.DELETED, deleted_count=2)
    other_source = queued_result("job-other", enumerated_count=0, source_id=OTHER_SOURCE_ID)
    for record in (waiting, judging, executing, no_finish, finished, other_source):
        seed_result(deletions_store, record)
    before = snapshot(deletions_store)
    untouched_ids = [
        deletion_result_record_id("job-deleted"),
        deletion_result_record_id("job-other"),
    ]

    discarded = manager.discard_source_crawls(SOURCE_ID, LOCK)  # ロックは確認しない(案 8)

    assert sorted(discarded) == ["job-executing", "job-judging", "job-no-finish", "job-waiting"]
    for crawl_id in discarded:
        result = stored_result(deletions_store, crawl_id)
        assert (result.status, result.reason) == (
            DeletionStatus.DISCARDED,
            DeletionReason.SOURCE_DELETED,
        )
        assert result.ended_at == DEFAULT_NOW
        assert result.skipped_document_ids is None  # 同じ書き込みで削除(K35)
    # 実行中のものの記録済みの件数と、受理の事実・ダイジェストは残る。
    executing_after = stored_result(deletions_store, "job-executing")
    assert executing_after.deleted_count == 4
    assert executing_after.finish_request_digest == "d" * 64
    after = snapshot(deletions_store)
    # 終端状態の結果と、ほかのソースの結果は変わらない。
    assert {record_id: after[record_id] for record_id in untouched_ids} == {
        record_id: before[record_id] for record_id in untouched_ids
    }


def test_discarding_again_changes_nothing(  # E-43(順 1 の冪等)
    manager: DeletionManager, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    assert manager.discard_source_crawls(SOURCE_ID, LOCK) == ["job-a"]
    before = snapshot(deletions_store)
    writes = len(deletions_store.write_calls())

    assert manager.discard_source_crawls(SOURCE_ID, LOCK) == []

    assert snapshot(deletions_store) == before
    assert len(deletions_store.write_calls()) == writes


def test_a_result_that_became_terminal_meanwhile_is_not_overwritten(
    manager: DeletionManager, deletions_store: InMemoryStore, results: DeletionResults
) -> None:
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))

    def finish_by_itself() -> None:
        current = results.fetch_result("job-a")
        assert current is not None
        results.transition_to_terminal(current, DeletionStatus.DELETED)

    deletions_store.behavior.before(
        store_ops.FETCH, finish_by_itself, key=deletion_result_record_id("job-a")
    )

    assert manager.discard_source_crawls(SOURCE_ID, LOCK) == []
    assert stored_result(deletions_store, "job-a").status is DeletionStatus.DELETED


def test_a_conflict_is_reread_and_retried(
    manager: DeletionManager, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    deletions_store.behavior.inject(
        store_ops.REPLACE,
        Conflict(),
        key=deletion_result_record_id("job-a"),
        times=DISCARD_ATTEMPTS - 1,
    )

    assert manager.discard_source_crawls(SOURCE_ID, LOCK) == ["job-a"]
    assert stored_result(deletions_store, "job-a").status is DeletionStatus.DISCARDED


def test_conflicts_beyond_the_attempt_limit_raise_a_retryable_error_and_write_nothing(
    manager: DeletionManager, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    deletions_store.behavior.inject(
        store_ops.REPLACE,
        Conflict(),
        key=deletion_result_record_id("job-a"),
        times=DISCARD_ATTEMPTS,
    )

    with pytest.raises(UnavailableError):
        manager.discard_source_crawls(SOURCE_ID, LOCK)

    assert stored_result(deletions_store, "job-a").status is DeletionStatus.RUNNING
    assert len(deletions_store.behavior.calls_of(store_ops.REPLACE)) == DISCARD_ATTEMPTS
    # 再実行すると、続きから完了する(冪等)。
    assert manager.discard_source_crawls(SOURCE_ID, LOCK) == ["job-a"]


# --- 実行中の削除との競合(D-41、D-42) ---


def test_a_discard_that_lands_before_the_judging_write_stops_the_deletion(  # D-41
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    owned_lock: LockInfo,
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=2, expired=3)
    deletions_store.behavior.before(
        store_ops.REPLACE,
        lambda: manager.discard_source_crawls(SOURCE_ID, LOCK),
        key=RESULT_ID,
    )

    outcome = manager.processor.process(CRAWL_ID)

    result = stored_result(deletions_store)
    assert outcome is DeletionOutcome.CLOSED
    assert (result.status, result.reason) == (
        DeletionStatus.DISCARDED,
        DeletionReason.SOURCE_DELETED,
    )
    assert result.deletion_started_at is None  # 削除側の書き込みは、終端状態を上書きしない
    assert result.finish_request_digest == "d" * 64
    assert search_index.write_calls() == []  # バッチは始まらない
    assert remaining(search_index, scenario.expired) == set(scenario.expired)


def test_a_result_that_cannot_be_read_stops_the_deletion_without_recreating_it(  # D-41(404)
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
) -> None:
    seed_scenario(search_index, deletions_store, seen=2, expired=3)
    deletions_store.behavior.before(
        store_ops.REPLACE, lambda: deletions_store.delete(RESULT_ID), key=RESULT_ID
    )

    outcome = manager.processor.process(CRAWL_ID)

    assert outcome is DeletionOutcome.CLOSED
    assert deletions_store.body_of(RESULT_ID) is None
    assert search_index.write_calls() == []


def test_a_waiting_result_discarded_with_its_predecessor_is_never_judged(  # D-42
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
) -> None:
    seed_scenario(search_index, deletions_store, seen=2, expired=3)  # 先行(CRAWL_ID)
    seed_result(
        deletions_store,
        queued_result("job-b", enumerated_count=2, finish_received_at=DEFAULT_NOW),  # 待機中の後続
    )

    manager.discard_source_crawls(SOURCE_ID, LOCK)

    assert stored_result(deletions_store, "job-b").status is DeletionStatus.DISCARDED
    assert manager.processor.process("job-b") is DeletionOutcome.CLOSED
    assert manager.worker.run_once() is False  # 待ち行列は空
    assert search_index.behavior.calls == []  # 判定に進まない(検索インデックスを読まない)


def test_the_queue_head_discarded_between_the_scan_and_the_read_is_closed(  # D-42
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
) -> None:
    seed_scenario(search_index, deletions_store, seen=2, expired=3)
    deletions_store.behavior.before(
        store_ops.FETCH,
        lambda: manager.discard_source_crawls(SOURCE_ID, LOCK),
        key=RESULT_ID,
    )

    assert manager.worker.run_once() is True  # 走査では先頭だったが、読み直すと終端状態

    assert stored_result(deletions_store).status is DeletionStatus.DISCARDED
    assert search_index.behavior.calls == []


# --- 実行中のバッチとの排他(D-74) ---


def test_a_discard_waits_for_the_running_batch_and_the_next_batch_never_starts(  # D-74(a)(b)(c)
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
) -> None:
    scenario = seed_scenario(search_index, deletions_store, seen=4, expired=7, min_delete_count=100)
    seed_result(
        deletions_store,
        queued_result(
            "job-b", enumerated_count=4, finish_received_at=DEFAULT_NOW, min_delete_count=100
        ),
    )  # 同じソースで待機中の後続
    gate = Gate()
    search_index.behavior.before(index_ops.DELETE, gate.pass_through, key=scenario.expired[0])
    deletes_when_the_discard_returned: list[int] = []

    def discard() -> list[str]:
        discarded_crawl_ids = manager.discard_source_crawls(SOURCE_ID, LOCK)
        deletes_when_the_discard_returned.append(
            len(search_index.behavior.calls_of(index_ops.DELETE))
        )
        return discarded_crawl_ids

    deleter = Background(lambda: manager.processor.process(CRAWL_ID))
    gate.wait_until_arrived()  # 1 バッチ目の途中(最初の文書の削除の直前)で止まっている
    discarder = Background(discard)
    assert discarder.is_blocked()  # バッチが終わるまで待たされる(バッチ内で止まれば待ち続ける)
    gate.release()
    deleter.join()
    discarder.join()

    assert deleter.value is DeletionOutcome.CLOSED
    assert sorted(discarder.value) == [CRAWL_ID, "job-b"]  # 待機中の結果も、応答の前に破棄される
    for crawl_id in (CRAWL_ID, "job-b"):
        assert stored_result(deletions_store, crawl_id).status is DeletionStatus.DISCARDED
    # 実行中だった 1 バッチ分だけが削除され、次のバッチは前確認で止まる。
    assert remaining(search_index, scenario.expired) == set(scenario.expired[BATCH_SIZE:])
    # 応答が返った時点で、そのソースの削除バッチは動いていない(その後も削除は増えない)。
    assert deletes_when_the_discard_returned == [BATCH_SIZE]
    assert len(search_index.behavior.calls_of(index_ops.DELETE)) == BATCH_SIZE


# --- ソース削除 2: 文書の全削除(D-90、E-43) ---


def test_documents_are_deleted_only_after_the_running_batch_of_the_source_ends(  # S3
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    owned_lock: LockInfo,
) -> None:
    """ソース削除 2 も、実行中のバッチと重ならない(バッチの途中の文書を巻き込まない)。"""
    scenario = seed_scenario(search_index, deletions_store, seen=4, expired=7, min_delete_count=100)
    gate = Gate()
    search_index.behavior.before(index_ops.DELETE, gate.pass_through, key=scenario.expired[0])

    deleter = Background(lambda: manager.processor.process(CRAWL_ID))
    gate.wait_until_arrived()  # 1 バッチ目の途中(最初の文書の削除の直前)で止まっている
    documents_deleter = Background(lambda: manager.delete_source_documents(SOURCE_ID, owned_lock))
    assert documents_deleter.is_blocked()  # バッチが終わるまで待たされる
    assert search_index.behavior.calls_of(index_ops.DELETE_BY_QUERY) == []
    gate.release()
    deleter.join()
    documents_deleter.join()

    assert deleter.error is None
    assert documents_deleter.error is None
    # 実行中だった 1 バッチ分の削除(3 件)が先で、そのあとに `delete_by_query` が走る。
    operations = [
        call.operation
        for call in search_index.behavior.calls_of(index_ops.DELETE, index_ops.DELETE_BY_QUERY)
    ]
    assert operations[: BATCH_SIZE + 1] == [index_ops.DELETE] * BATCH_SIZE + [
        index_ops.DELETE_BY_QUERY
    ]
    assert documents_deleter.value == 4 + 7 - BATCH_SIZE  # 残っていた分だけを消す
    assert search_index.document_ids() == []


@pytest.mark.parametrize(
    "lock_state",
    ["no_lock_document", "expired", "other_owner", "other_job"],
)
def test_without_the_lock_nothing_is_written_and_the_request_is_rejected(  # 案 8、api 3.4
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    lock_state: str,
) -> None:
    documents = seed_source_documents(search_index, 3)
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    seed_state = {
        "expired": lambda: seed_lock(
            jobs_store, owner=LOCK.owner, job_id=LOCK.job_id, lease_expires_at=DEFAULT_NOW
        ),
        "other_owner": lambda: seed_lock(jobs_store, owner="crawler-2", job_id=LOCK.job_id),
        "other_job": lambda: seed_lock(jobs_store, owner=LOCK.owner, job_id="job-other"),
        "no_lock_document": lambda: None,
    }[lock_state]
    seed_state()
    before = snapshot(deletions_store)

    with pytest.raises(LockNotOwnedError) as rejected:
        manager.delete_source_documents(SOURCE_ID, LOCK)
    with pytest.raises(LockNotOwnedError):
        manager.delete_source_records(SOURCE_ID, LOCK)

    assert (rejected.value.status_code, rejected.value.code, rejected.value.retryable) == (
        409,
        "lock_not_owned",
        False,
    )
    assert search_index.behavior.calls == []  # 検索インデックスに何もしない(refresh も)
    assert deletions_store.write_calls() == []
    assert snapshot(deletions_store) == before
    assert remaining(search_index, documents) == set(documents)


def test_a_failure_reading_the_lock_never_means_it_is_owned(
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    owned_lock: LockInfo,
) -> None:
    """ロック文書を読めない(OpenSearch の障害)ときは、所有とみなさず、何も削除しない。"""
    documents = seed_source_documents(search_index, 3)
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))
    before = snapshot(deletions_store)
    lock_record_id = f"lock-{SOURCE_ID}"
    jobs_store.behavior.inject(
        store_ops.FETCH, OpenSearchUnavailableError("http_503"), key=lock_record_id, times=2
    )

    with pytest.raises(OpenSearchUnavailableError):
        manager.delete_source_documents(SOURCE_ID, owned_lock)
    with pytest.raises(OpenSearchUnavailableError):
        manager.delete_source_records(SOURCE_ID, owned_lock)

    assert search_index.behavior.calls_of(index_ops.DELETE_BY_QUERY) == []
    assert remaining(search_index, documents) == set(documents)
    assert snapshot(deletions_store) == before
    assert deletions_store.write_calls() == []


def test_discard_does_not_check_the_lock(
    manager: DeletionManager, deletions_store: InMemoryStore, jobs_store: InMemoryStore
) -> None:
    seed_result(deletions_store, queued_result("job-a", enumerated_count=0))

    manager.discard_source_crawls(SOURCE_ID, LOCK)

    assert jobs_store.behavior.calls == []  # ロック文書を読まない(案 8)


def test_all_documents_of_the_source_are_deleted_and_other_sources_are_untouched(
    manager: DeletionManager, search_index: InMemorySearchIndex, owned_lock: LockInfo
) -> None:
    documents = seed_source_documents(search_index, 5)
    others = seed_source_documents(search_index, 3, source_id=OTHER_SOURCE_ID, base=500)

    deleted = manager.delete_source_documents(SOURCE_ID, owned_lock)

    assert deleted == 5
    assert remaining(search_index, documents) == set()
    assert remaining(search_index, others) == set(others)  # `source_id` の条件で絞る


def test_documents_written_but_not_yet_refreshed_are_deleted_by_the_first_run(  # D-90(b)
    manager: DeletionManager, search_index: InMemorySearchIndex, owned_lock: LockInfo
) -> None:
    documents = ids(100, 3)
    seed_documents(search_index, documents, last_seen_at=SEEN_AT, searchable=False)

    deleted = manager.delete_source_documents(SOURCE_ID, owned_lock)

    # 実行前の refresh で検索の対象になるので、1 回で消える(再実行が要らない)。
    assert deleted == 3
    assert remaining(search_index, documents) == set()
    assert len(search_index.behavior.calls_of(index_ops.DELETE_BY_QUERY)) == 1


def test_documents_updated_or_registered_during_the_deletion_are_removed_by_a_rerun(  # D-90(a)
    manager: DeletionManager, search_index: InMemorySearchIndex, owned_lock: LockInfo
) -> None:
    documents = seed_source_documents(search_index, 5)
    reregistered = ids(900, 1)[0]

    def concurrent_writes() -> None:
        search_index.seed(  # 更新: 検索時点から版が変わるので、その回は競合して消えない
            documents[0],
            {"source_id": SOURCE_ID, "last_seen_at": "2026-11-11T00:00:00.000Z"},
            searchable=False,
        )
        search_index.seed(  # 再登録: まだ検索の対象でない
            reregistered,
            {"source_id": SOURCE_ID, "last_seen_at": "2026-11-11T00:00:00.000Z"},
            searchable=False,
        )

    search_index.behavior.before(index_ops.DELETE_BY_QUERY, concurrent_writes)

    deleted = manager.delete_source_documents(SOURCE_ID, owned_lock)

    # 1 回目は競合した 1 件を除く 4 件、再実行で競合した 1 件と再登録された 1 件。
    assert deleted == 6
    assert remaining(search_index, (*documents, reregistered)) == set()  # 再登録が勝つ扱いはしない
    assert len(search_index.behavior.calls_of(index_ops.DELETE_BY_QUERY)) == 2


def test_a_count_that_never_reaches_zero_stops_at_the_rerun_limit_with_a_retryable_error(  # D-90(c)
    manager: DeletionManager, search_index: InMemorySearchIndex, owned_lock: LockInfo
) -> None:
    seed_source_documents(search_index, 3)
    runs = 1 + MAX_RERUNS
    search_index.behavior.inject(index_ops.COUNT, 3, times=runs)

    with pytest.raises(UnavailableError) as stopped:
        manager.delete_source_documents(SOURCE_ID, owned_lock)

    assert stopped.value.reason == "documents_remaining"
    assert len(search_index.behavior.calls_of(index_ops.DELETE_BY_QUERY)) == runs  # 無制限にしない
    # 再実行すると、残りの確認が通って成功する。すでに消えた分は数えない(E-43)。
    assert manager.delete_source_documents(SOURCE_ID, owned_lock) == 0


def test_a_stalled_refresh_ends_in_a_retryable_error_not_a_false_success(  # D-90(b)
    manager: DeletionManager, search_index: InMemorySearchIndex, owned_lock: LockInfo
) -> None:
    seed_source_documents(search_index, 3)
    search_index.refresh_stalled = True  # 完了後の refresh が反映されず、`_count` が古いまま

    with pytest.raises(UnavailableError):
        manager.delete_source_documents(SOURCE_ID, owned_lock)

    assert len(search_index.behavior.calls_of(index_ops.DELETE_BY_QUERY)) == 1 + MAX_RERUNS
    search_index.refresh_stalled = False
    assert manager.delete_source_documents(SOURCE_ID, owned_lock) == 0  # 再実行で完了する


def test_a_failure_in_the_middle_is_completed_by_running_it_again(  # E-43
    manager: DeletionManager, search_index: InMemorySearchIndex, owned_lock: LockInfo
) -> None:
    documents = seed_source_documents(search_index, 4)
    search_index.behavior.inject(
        index_ops.DELETE_BY_QUERY, OpenSearchUnavailableError("connection_timeout"), times=1
    )

    with pytest.raises(OpenSearchUnavailableError):
        manager.delete_source_documents(SOURCE_ID, owned_lock)
    assert remaining(search_index, documents) == set(documents)

    assert manager.delete_source_documents(SOURCE_ID, owned_lock) == 4
    assert manager.delete_source_documents(SOURCE_ID, owned_lock) == 0  # 何度でも同じ結果


def test_the_lock_is_checked_again_before_each_rerun(  # 別のジョブがロックを取った後の再実行を防ぐ
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
    owned_lock: LockInfo,
) -> None:
    documents = seed_source_documents(search_index, 3)
    # 1 回目の `delete_by_query` が競合して文書が残り、再実行に進む。その前にリースが切れる。
    search_index.behavior.before(
        index_ops.DELETE_BY_QUERY,
        lambda: search_index.seed(
            documents[0], {"source_id": SOURCE_ID, "last_seen_at": "x"}, searchable=False
        ),
    )
    jobs_store.behavior.before(store_ops.FETCH, lambda: None, key=f"lock-{SOURCE_ID}")
    jobs_store.behavior.before(
        store_ops.FETCH,
        lambda: seed_lock(
            jobs_store, owner=LOCK.owner, job_id=LOCK.job_id, lease_expires_at=DEFAULT_NOW
        ),
        key=f"lock-{SOURCE_ID}",
    )

    with pytest.raises(LockNotOwnedError):
        manager.delete_source_documents(SOURCE_ID, owned_lock)

    assert len(search_index.behavior.calls_of(index_ops.DELETE_BY_QUERY)) == 1


def test_delete_by_query_is_always_limited_to_the_source(
    deletion_config: DeletionConfig,
    results: DeletionResults,
    jobs_reader: StoreJobsReader,
    clock: FixedClock,
    owned_lock: LockInfo,
) -> None:
    class RecordingIndex(InMemorySearchIndex):
        def __init__(self) -> None:
            super().__init__()
            self.filters: list[DocumentFilter] = []

        def delete_by_query(self, document_filter: DocumentFilter) -> DeleteByQueryResult:
            self.filters.append(document_filter)
            return super().delete_by_query(document_filter)

    recording = RecordingIndex()
    manager = create_deletion_manager(
        deletion_config, results=results, search_index=recording, jobs=jobs_reader, clock=clock
    )

    manager.delete_source_documents(SOURCE_ID, owned_lock)

    assert recording.filters == [DocumentFilter(source_id=SOURCE_ID)]


# --- ソース削除 3: 削除記録の削除(E-43) ---


def test_the_generation_and_every_result_of_the_source_are_deleted(
    manager: DeletionManager, deletions_store: InMemoryStore, owned_lock: LockInfo
) -> None:
    deletions_store.seed(deletion_record_id(SOURCE_ID), make_generation().to_body())
    for record in (
        make_result(crawl_id="job-running"),
        queued_result("job-waiting", enumerated_count=0),
        make_result(crawl_id="job-done", status=DeletionStatus.DELETED),
        make_result(crawl_id="job-discarded", status=DeletionStatus.DISCARDED),
    ):
        seed_result(deletions_store, record)
    deletions_store.seed(
        deletion_record_id(OTHER_SOURCE_ID), make_generation(source_id=OTHER_SOURCE_ID).to_body()
    )
    seed_result(deletions_store, make_result(crawl_id="job-other", source_id=OTHER_SOURCE_ID))

    assert manager.delete_source_records(SOURCE_ID, owned_lock) is True

    assert deletions_store.record_ids() == sorted(
        [deletion_record_id(OTHER_SOURCE_ID), deletion_result_record_id("job-other")]
    )


def test_deleting_the_records_again_succeeds_with_false(  # E-43
    manager: DeletionManager, deletions_store: InMemoryStore, owned_lock: LockInfo
) -> None:
    seed_result(deletions_store, make_result())

    assert manager.delete_source_records(SOURCE_ID, owned_lock) is True
    assert manager.delete_source_records(SOURCE_ID, owned_lock) is False


def test_the_whole_source_deletion_can_be_run_again_after_a_stop_in_the_middle(  # D-35、D-84、E-43
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    owned_lock: LockInfo,
) -> None:
    """`deletion_result` がなくても(開始通知を伴わなくても)、1〜3 は受理条件の確認なしで動く。"""
    scenario = seed_scenario(
        search_index, deletions_store, seen=3, expired=4, other_source_expired=2
    )
    deletions_store.seed(deletion_record_id(SOURCE_ID), make_generation().to_body())

    manager.discard_source_crawls(SOURCE_ID, LOCK)
    manager.delete_source_documents(SOURCE_ID, owned_lock)
    # ここでジョブがリース切れで止まった。再実行すると、1〜3 のすべてが成功する。
    assert manager.discard_source_crawls(SOURCE_ID, LOCK) == []
    assert manager.delete_source_documents(SOURCE_ID, owned_lock) == 0
    assert manager.delete_source_records(SOURCE_ID, owned_lock) is True

    assert remaining(search_index, scenario.seen + scenario.expired) == set()
    assert remaining(search_index, scenario.others) == set(scenario.others)
    assert deletions_store.record_ids() == []


def test_documents_of_a_source_without_any_deletion_result_are_deleted(  # D-84
    manager: DeletionManager,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    owned_lock: LockInfo,
) -> None:
    documents = seed_source_documents(search_index, 2)

    assert manager.delete_source_documents(SOURCE_ID, owned_lock) == 2
    assert remaining(search_index, documents) == set()
    assert deletions_store.behavior.calls == []
