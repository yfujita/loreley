"""`InMemoryRepository` 固有の機能の自己テスト。

契約(同じ結果区分)は `test_repository_contract.py` が、OpenSearch 実装と同じテストで確かめる。
ここは、後続のフェーズが競合・割り込み・部分失敗を再現するために使う口(フック・差し替え・
バルク削除の失敗の注入)と、呼び出しの記録を確かめる。
"""

import threading

import pytest

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.infrastructure.opensearch import (
    AlreadyExists,
    BulkDeleteResult,
    Conflict,
    RecordFilter,
    SortKey,
    Written,
)
from tests.fakes import in_memory_repository as ops
from tests.fakes.in_memory_repository import InMemoryRepository

JOIN_TIMEOUT_SECONDS = 5.0


def test_a_hook_runs_before_the_operation_and_can_change_the_record_it_will_conflict_with() -> None:
    repository = InMemoryRepository()
    repository.create("lock-s1", {"owner": "a"})
    read = repository.fetch("lock-s1")
    assert read is not None
    # 読んだ後・書く前に、別の書き手が書き込む(競合の再現)。
    repository.behavior.before(
        ops.REPLACE,
        lambda: repository.seed("lock-s1", {"owner": "other"}),
    )

    outcome = repository.replace_if_unchanged(
        "lock-s1", {"owner": "a"}, seq_no=read.seq_no, primary_term=read.primary_term
    )

    assert outcome == Conflict()
    assert repository.body_of("lock-s1") == {"owner": "other"}


def test_two_concurrent_creates_of_the_same_id_succeed_exactly_once() -> None:
    repository = InMemoryRepository()
    outcomes: list[object] = []
    # 待ち・合流に上限を置く(不具合で、テストが止まらなくならないように)。
    start = threading.Barrier(8, timeout=JOIN_TIMEOUT_SECONDS)

    def create() -> None:
        start.wait()
        outcomes.append(repository.create("lock-s1", {"owner": "x"}))

    threads = [threading.Thread(target=create, daemon=True) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=JOIN_TIMEOUT_SECONDS)
    assert not any(thread.is_alive() for thread in threads)

    assert sum(isinstance(outcome, Written) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, AlreadyExists) for outcome in outcomes) == 7


def test_a_response_can_be_replaced_and_an_error_can_be_injected() -> None:
    repository = InMemoryRepository()
    repository.behavior.inject(ops.CREATE, AlreadyExists())
    repository.behavior.inject(ops.FETCH, StoreUnavailableError("connection_timeout"))

    assert repository.create("job-1", {}) == AlreadyExists()  # 差し替えた呼び出しは、書かない
    assert repository.record_ids() == []
    with pytest.raises(StoreUnavailableError):
        repository.fetch("job-1")
    assert repository.fetch("job-1") is None  # 注入は 1 回だけ


def test_the_calls_and_the_write_calls_are_recorded_in_order() -> None:
    repository = InMemoryRepository()

    repository.create("a", {})
    repository.fetch("a")
    repository.list_records(RecordFilter(), [SortKey("x")], limit=1)
    repository.delete_ids(["a"])

    assert [call.operation for call in repository.behavior.calls] == [
        ops.CREATE,
        ops.FETCH,
        ops.LIST,
        ops.DELETE_IDS,
    ]
    assert repository.write_calls() == [ops.CREATE, ops.DELETE_IDS]


def test_a_failure_of_bulk_delete_can_be_kept_for_several_calls() -> None:
    repository = InMemoryRepository()
    repository.seed("a", {})
    repository.seed("b", {})
    repository.fail_bulk_delete_of(["a"], times=2)

    results = [repository.delete_ids(["a", "b"]) for _ in range(3)]

    assert [r.failed_ids for r in results] == [("a",), ("a",), ()]
    assert repository.record_ids() == []


def test_a_failure_of_bulk_delete_can_be_kept_until_removed() -> None:
    repository = InMemoryRepository()
    repository.seed("a", {})
    repository.fail_bulk_delete_of(["a"], times=None)

    assert [repository.delete_ids(["a"]) for _ in range(5)] == [BulkDeleteResult(("a",))] * 5
    assert repository.record_ids() == ["a"]


def test_the_scan_snapshot_is_not_affected_by_writes_after_it_starts() -> None:
    repository = InMemoryRepository()
    repository.seed("a", {"document_id": "1"})

    with repository.scan(RecordFilter(), sort=[SortKey("document_id")]) as pages:
        repository.seed("b", {"document_id": "2"})
        ids = [record.id for page in pages for record in page]

    assert ids == ["a"]
