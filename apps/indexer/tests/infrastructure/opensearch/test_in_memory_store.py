import threading

import pytest

from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    Deleted,
    NotFound,
    RecordFilter,
    SortKey,
    Written,
)
from tests.fakes import in_memory_store as ops
from tests.fakes.concurrency import SlowReadDict, run_concurrently
from tests.fakes.in_memory_store import InMemoryStore


def test_save_overwrites_and_fetch_returns_a_copy_with_the_version(
    deletions_store: InMemoryStore,
) -> None:
    first = deletions_store.save("r1", {"status": "running"})
    second = deletions_store.save("r1", {"status": "failed"})

    assert first == Written(seq_no=0, primary_term=1, created=True)
    assert second == Written(seq_no=1, primary_term=1, created=False)
    fetched = deletions_store.fetch("r1")
    assert fetched.source == {"status": "failed"}
    fetched.source["status"] = "mutated"
    assert deletions_store.body_of("r1") == {"status": "failed"}
    assert deletions_store.fetch("missing") is None


def test_replace_if_unchanged_detects_a_concurrent_update(deletions_store: InMemoryStore) -> None:
    deletions_store.save("r1", {"status": "running"})
    read = deletions_store.fetch("r1")
    deletions_store.seed("r1", {"status": "discarded"})  # 別の書き手

    outcome = deletions_store.replace_if_unchanged(
        "r1", {"status": "failed"}, seq_no=read.seq_no, primary_term=read.primary_term
    )

    assert outcome == Conflict()
    assert deletions_store.body_of("r1") == {"status": "discarded"}


def test_replace_if_unchanged_on_a_missing_record_is_not_found(
    deletions_store: InMemoryStore,
) -> None:
    assert deletions_store.replace_if_unchanged("r1", {}, seq_no=0, primary_term=1) == NotFound()


def test_delete_removes_the_record_and_is_idempotent(deletions_store: InMemoryStore) -> None:
    deletions_store.save("r1", {})
    assert deletions_store.delete("r1") == Deleted()
    assert deletions_store.delete("r1") == NotFound()


def seed_results(store: InMemoryStore) -> None:
    store.seed(
        "deletion_result-c1",
        {
            "source_id": "s1",
            "status": "running",
            "finish_received_at": "2026-11-01T00:00:00.000Z",
            "crawl_id": "c1",
        },
    )
    store.seed(
        "deletion_result-c2",
        {
            "source_id": "s1",
            "status": "running",
            "finish_received_at": "2026-11-01T00:00:00.000Z",
            "crawl_id": "c2",
        },
    )
    store.seed("deletion_result-c3", {"source_id": "s1", "status": "running", "crawl_id": "c3"})
    store.seed(
        "deletion_result-c4",
        {
            "source_id": "s1",
            "status": "deleted",
            "finish_received_at": "2026-10-01T00:00:00.000Z",
            "crawl_id": "c4",
        },
    )
    store.seed(
        "deletion_result-c5",
        {
            "source_id": "s2",
            "status": "running",
            "finish_received_at": "2026-11-02T00:00:00.000Z",
            "crawl_id": "c5",
        },
    )


def test_list_records_filters_by_equality_membership_and_presence(
    deletions_store: InMemoryStore,
) -> None:
    seed_results(deletions_store)

    waiting = deletions_store.list_records(
        RecordFilter(
            equals={"source_id": "s1"},
            one_of={"status": ["running"]},
            exists=("finish_received_at",),
        ),
        [SortKey("finish_received_at"), SortKey("crawl_id")],
        limit=10,
    )
    assert [record.id for record in waiting] == ["deletion_result-c1", "deletion_result-c2"]

    not_received = deletions_store.list_records(
        RecordFilter(equals={"source_id": "s1"}, missing=("finish_received_at",)), [], limit=10
    )
    assert [record.id for record in not_received] == ["deletion_result-c3"]


def test_list_records_sorts_by_multiple_keys_with_missing_values_last(
    deletions_store: InMemoryStore,
) -> None:
    seed_results(deletions_store)

    ascending = deletions_store.list_records(
        RecordFilter(equals={"source_id": "s1"}),
        [SortKey("finish_received_at"), SortKey("crawl_id")],
        limit=10,
    )
    assert [r.id[-2:] for r in ascending] == ["c4", "c1", "c2", "c3"]

    descending = deletions_store.list_records(
        RecordFilter(equals={"source_id": "s1"}),
        [SortKey("finish_received_at", descending=True), SortKey("crawl_id", descending=True)],
        limit=10,
    )
    assert [r.id[-2:] for r in descending] == ["c2", "c1", "c4", "c3"]


def test_list_records_applies_the_limit_and_rejects_invalid_limits(
    deletions_store: InMemoryStore,
) -> None:
    seed_results(deletions_store)
    assert len(deletions_store.list_records(RecordFilter(), [SortKey("crawl_id")], limit=2)) == 2
    with pytest.raises(ValueError, match="limit"):
        deletions_store.list_records(RecordFilter(), [], limit=0)


def test_list_sees_writes_immediately(deletions_store: InMemoryStore) -> None:
    deletions_store.save("r1", {"source_id": "s1"})
    assert (
        len(deletions_store.list_records(RecordFilter(equals={"source_id": "s1"}), [], limit=5))
        == 1
    )


def test_hook_and_injection_work_like_the_search_index_fake(deletions_store: InMemoryStore) -> None:
    deletions_store.save("r1", {"status": "running"})
    read = deletions_store.fetch("r1")
    deletions_store.behavior.before(
        ops.REPLACE, lambda: deletions_store.seed("r1", {"status": "discarded"})
    )
    assert (
        deletions_store.replace_if_unchanged(
            "r1", {"status": "failed"}, seq_no=read.seq_no, primary_term=read.primary_term
        )
        == Conflict()
    )

    deletions_store.behavior.inject(ops.SAVE, Conflict(), times=2)
    assert [deletions_store.save("r2", {}) for _ in range(3)][:2] == [Conflict(), Conflict()]
    assert deletions_store.write_calls() == [ops.SAVE, ops.REPLACE, ops.SAVE, ops.SAVE, ops.SAVE]


def test_replace_with_a_different_primary_term_conflicts(deletions_store: InMemoryStore) -> None:
    deletions_store.save("r1", {"status": "running"})
    read = deletions_store.fetch("r1")
    assert (
        deletions_store.replace_if_unchanged(
            "r1", {}, seq_no=read.seq_no, primary_term=read.primary_term + 1
        )
        == Conflict()
    )
    assert deletions_store.body_of("r1") == {"status": "running"}


def test_concurrent_replace_with_the_same_version_lets_only_one_succeed(
    deletions_store: InMemoryStore,
) -> None:
    deletions_store.save("r1", {"status": "running"})
    read = deletions_store.fetch("r1")
    deletions_store._records = SlowReadDict(deletions_store._records)
    barrier = threading.Barrier(2, timeout=5)
    for _ in range(2):
        deletions_store.behavior.before(ops.REPLACE, lambda: barrier.wait())
    outcomes = run_concurrently(
        [
            lambda: deletions_store.replace_if_unchanged(
                "r1", {}, seq_no=read.seq_no, primary_term=read.primary_term
            )
            for _ in range(2)
        ]
    )

    assert sorted(type(outcome).__name__ for outcome in outcomes) == ["Conflict", "Written"]


def test_hook_for_a_key_waits_for_a_call_with_that_key(deletions_store: InMemoryStore) -> None:
    deletions_store.save("r1", {})
    deletions_store.save("r2", {})
    deletions_store.behavior.inject(ops.DELETE, Conflict(), key="r2")

    assert deletions_store.delete("r1") == Deleted()
    assert deletions_store.delete("r2") == Conflict()
    assert deletions_store.delete("r2") == Deleted()
