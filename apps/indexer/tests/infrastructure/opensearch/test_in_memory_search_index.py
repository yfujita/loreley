"""インメモリ fake の自己テスト。後続フェーズのテストが、fake の挙動を前提にできるようにする。"""

import threading
from datetime import UTC, datetime

import pytest

from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    DeleteByQueryResult,
    Deleted,
    DocumentFilter,
    NotFound,
    OpenSearchUnavailableError,
    Unchanged,
    Updated,
    Written,
)
from tests.fakes import in_memory_search_index as ops
from tests.fakes.behavior import Call
from tests.fakes.concurrency import SlowReadDict, run_concurrently
from tests.fakes.in_memory_search_index import InMemorySearchIndex

T1 = datetime(2026, 11, 1, tzinfo=UTC)
T2 = datetime(2026, 11, 2, tzinfo=UTC)
T3 = datetime(2026, 11, 3, tzinfo=UTC)


def doc(
    source_id: str = "s1", last_seen_at: str = "2026-11-02T00:00:00.000Z", **extra: object
) -> dict:
    return {"source_id": source_id, "last_seen_at": last_seen_at, **extra}


# --- 楽観ロック ---


def test_create_succeeds_once_then_conflicts(search_index: InMemorySearchIndex) -> None:
    assert isinstance(search_index.create("d1", doc()), Written)
    assert search_index.create("d1", doc()) == Conflict()


def test_fetch_returns_a_copy_with_the_version(search_index: InMemorySearchIndex) -> None:
    written = search_index.create("d1", doc(title="a"))
    assert isinstance(written, Written)

    fetched = search_index.fetch("d1")
    assert fetched is not None
    assert (fetched.seq_no, fetched.primary_term) == (written.seq_no, written.primary_term)

    fetched.source["title"] = "mutated"
    assert search_index.source_of("d1")["title"] == "a"
    assert search_index.fetch("missing") is None


def test_replace_succeeds_with_the_current_version_and_advances_it(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.create("d1", doc(title="a"))
    fetched = search_index.fetch("d1")

    outcome = search_index.replace_if_unchanged(
        "d1", doc(title="b"), seq_no=fetched.seq_no, primary_term=fetched.primary_term
    )

    assert isinstance(outcome, Written)
    assert outcome.seq_no > fetched.seq_no
    assert search_index.source_of("d1")["title"] == "b"


def test_replace_with_a_stale_version_conflicts_and_keeps_the_document(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.create("d1", doc(title="a"))
    stale = search_index.fetch("d1")
    search_index.seed("d1", doc(title="other writer"))

    outcome = search_index.replace_if_unchanged(
        "d1", doc(title="mine"), seq_no=stale.seq_no, primary_term=stale.primary_term
    )

    assert outcome == Conflict()
    assert search_index.source_of("d1")["title"] == "other writer"


@pytest.mark.parametrize(
    ("mode", "expected"), [("not_found", NotFound()), ("conflict", Conflict())]
)
def test_conditional_write_to_a_missing_document_follows_the_configured_response(
    mode: str, expected: object
) -> None:
    index = InMemorySearchIndex(missing_document_conditional_write=mode)
    assert index.replace_if_unchanged("d1", doc(), seq_no=1, primary_term=1) == expected
    assert index.delete_if_unchanged("d1", seq_no=1, primary_term=1) == expected


def test_delete_with_a_stale_version_conflicts(search_index: InMemorySearchIndex) -> None:
    search_index.create("d1", doc())
    stale = search_index.fetch("d1")
    search_index.seed("d1", doc())

    assert (
        search_index.delete_if_unchanged("d1", seq_no=stale.seq_no, primary_term=stale.primary_term)
        == Conflict()
    )
    current = search_index.fetch("d1")
    assert (
        search_index.delete_if_unchanged(
            "d1", seq_no=current.seq_no, primary_term=current.primary_term
        )
        == Deleted()
    )
    assert search_index.fetch("d1") is None


def test_replace_and_delete_with_a_different_primary_term_conflict(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.create("d1", doc())
    read = search_index.fetch("d1")

    assert (
        search_index.replace_if_unchanged(
            "d1", doc(), seq_no=read.seq_no, primary_term=read.primary_term + 1
        )
        == Conflict()
    )
    assert (
        search_index.delete_if_unchanged(
            "d1", seq_no=read.seq_no, primary_term=read.primary_term + 1
        )
        == Conflict()
    )
    assert search_index.fetch("d1") is not None


def test_a_version_read_before_delete_and_recreate_is_stale(
    search_index: InMemorySearchIndex,
) -> None:
    """削除して作り直した文書に、古い版で書けない(ABA。削除も seq_no を進める)。"""
    search_index.create("d1", doc(title="first"))
    stale = search_index.fetch("d1")
    search_index.seed_removal("d1")
    search_index.create("d1", doc(title="recreated"))

    assert (
        search_index.replace_if_unchanged(
            "d1", doc(title="mine"), seq_no=stale.seq_no, primary_term=stale.primary_term
        )
        == Conflict()
    )
    assert (
        search_index.delete_if_unchanged("d1", seq_no=stale.seq_no, primary_term=stale.primary_term)
        == Conflict()
    )
    assert search_index.source_of("d1")["title"] == "recreated"


def _make_calls_meet_before_writing(search_index: InMemorySearchIndex, *operations: str) -> None:
    """各操作を 1 回ずつ、書き込みの直前でそろえてから同時に進める(フックはロックの外で動く)。"""
    search_index._documents = SlowReadDict(search_index._documents)
    barrier = threading.Barrier(len(operations), timeout=5)
    for operation in operations:
        search_index.behavior.before(operation, lambda: barrier.wait())


def test_concurrent_create_of_the_same_id_lets_only_one_succeed(
    search_index: InMemorySearchIndex,
) -> None:
    _make_calls_meet_before_writing(search_index, ops.CREATE, ops.CREATE)

    outcomes = run_concurrently(
        [lambda: search_index.create("d1", doc()), lambda: search_index.create("d1", doc())]
    )

    assert sorted(type(outcome).__name__ for outcome in outcomes) == ["Conflict", "Written"]


def test_concurrent_replace_with_the_same_version_lets_only_one_succeed(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.create("d1", doc())
    read = search_index.fetch("d1")
    _make_calls_meet_before_writing(search_index, ops.REPLACE, ops.REPLACE)

    outcomes = run_concurrently(
        [
            lambda: search_index.replace_if_unchanged(
                "d1", doc(), seq_no=read.seq_no, primary_term=read.primary_term
            )
            for _ in range(2)
        ]
    )

    assert sorted(type(outcome).__name__ for outcome in outcomes) == ["Conflict", "Written"]


def test_concurrent_delete_and_replace_with_the_same_version_lets_only_one_succeed(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.create("d1", doc())
    read = search_index.fetch("d1")
    _make_calls_meet_before_writing(search_index, ops.DELETE, ops.REPLACE)

    delete_outcome, replace_outcome = run_concurrently(
        [
            lambda: search_index.delete_if_unchanged(
                "d1", seq_no=read.seq_no, primary_term=read.primary_term
            ),
            lambda: search_index.replace_if_unchanged(
                "d1", doc(title="replaced"), seq_no=read.seq_no, primary_term=read.primary_term
            ),
        ]
    )

    # 先に進んだ側だけが成功する。負けた側は、文書が変わった(Conflict)か、
    # 消えた(fake の既定では NotFound)ことで失敗する。
    if isinstance(delete_outcome, Deleted):
        assert not isinstance(replace_outcome, Written)
        assert search_index.fetch("d1") is None
    else:
        assert isinstance(replace_outcome, Written)
        assert delete_outcome == Conflict()
        assert search_index.source_of("d1")["title"] == "replaced"


# --- last_seen_at の max 比較 ---


def test_raise_last_seen_at_updates_only_to_a_newer_value(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.seed("d1", doc(last_seen_at="2026-11-02T00:00:00.000Z", title="keep"))

    assert search_index.raise_last_seen_at("d1", T3) == Updated()
    assert search_index.source_of("d1") == doc(
        last_seen_at="2026-11-03T00:00:00.000Z", title="keep"
    )

    assert search_index.raise_last_seen_at("d1", T2) == Unchanged()  # 古い値には戻らない
    assert search_index.raise_last_seen_at("d1", T3) == Unchanged()  # 同じ値は書かない
    assert search_index.source_of("d1")["last_seen_at"] == "2026-11-03T00:00:00.000Z"


def test_unchanged_last_seen_at_does_not_advance_the_version(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.seed("d1", doc())
    before = search_index.fetch("d1")
    search_index.raise_last_seen_at("d1", T1)
    assert search_index.fetch("d1").seq_no == before.seq_no


def test_raise_last_seen_at_compares_instants_not_strings(
    search_index: InMemorySearchIndex,
) -> None:
    # 文字列では "2026-11-02T09:00:00+09:00" > "2026-11-02T00:30:00.000Z" だが、時刻は前。
    search_index.seed("d1", doc(last_seen_at="2026-11-02T09:00:00+09:00"))
    assert (
        search_index.raise_last_seen_at("d1", datetime(2026, 11, 2, 0, 30, tzinfo=UTC)) == Updated()
    )


def test_raise_last_seen_at_does_not_create_a_missing_document(
    search_index: InMemorySearchIndex,
) -> None:
    assert search_index.raise_last_seen_at("d1", T1) == NotFound()
    assert search_index.document_ids() == []


def test_last_seen_at_update_invalidates_a_version_read_earlier(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.seed("d1", doc(last_seen_at="2026-11-01T00:00:00.000Z"))
    stale = search_index.fetch("d1")
    search_index.raise_last_seen_at("d1", T3)
    assert (
        search_index.replace_if_unchanged(
            "d1", doc(), seq_no=stale.seq_no, primary_term=stale.primary_term
        )
        == Conflict()
    )


def test_raise_last_seen_at_on_a_document_without_last_seen_at_updates_it(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.seed("d1", {"source_id": "s1"})
    assert search_index.raise_last_seen_at("d1", T1) == Updated()
    assert search_index.source_of("d1")["last_seen_at"] == "2026-11-01T00:00:00.000Z"


# --- refresh の可視性 ---


def test_search_and_count_see_writes_only_after_refresh_but_fetch_is_realtime(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.create("d1", doc())

    assert search_index.fetch("d1") is not None
    assert search_index.count(DocumentFilter(source_id="s1")) == 0
    assert search_index.search_document_ids(DocumentFilter(), page_size=10, after=None) == []

    search_index.refresh()

    assert search_index.count(DocumentFilter(source_id="s1")) == 1
    assert search_index.search_document_ids(DocumentFilter(), page_size=10, after=None) == ["d1"]


def test_refresh_on_write_makes_every_write_searchable() -> None:
    index = InMemorySearchIndex(refresh_on_write=True)
    index.create("d1", doc())
    assert index.count(DocumentFilter()) == 1
    fetched = index.fetch("d1")
    index.delete_if_unchanged("d1", seq_no=fetched.seq_no, primary_term=fetched.primary_term)
    assert index.count(DocumentFilter()) == 0


def test_stalled_refresh_keeps_searches_stale(search_index: InMemorySearchIndex) -> None:
    search_index.refresh_stalled = True
    search_index.create("d1", doc())
    search_index.refresh()
    assert search_index.count(DocumentFilter()) == 0

    search_index.refresh_stalled = False
    search_index.refresh()
    assert search_index.count(DocumentFilter()) == 1


# --- 検索 ---


def test_filters_by_source_summary_status_and_last_seen_range(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.seed("a", doc("s1", "2026-11-01T00:00:00.000Z", summary_status="pending"))
    search_index.seed("b", doc("s1", "2026-11-02T00:00:00.000Z", summary_status="generated"))
    search_index.seed("c", doc("s2", "2026-11-02T00:00:00.000Z", summary_status="pending"))
    search_index.seed("d", {"source_id": "s1"})  # last_seen_at なし

    assert search_index.count(DocumentFilter(source_id="s1")) == 3
    assert search_index.count(DocumentFilter(summary_status="pending")) == 2
    assert search_index.count(DocumentFilter(source_id="s1", last_seen_at_gte=T2)) == 1  # b
    assert (
        search_index.count(DocumentFilter(source_id="s1", last_seen_at_lt=T2)) == 1
    )  # a (gte/lt は半開区間)
    assert search_index.count(DocumentFilter(last_seen_at_gte=T1, last_seen_at_lt=T3)) == 3


def test_search_after_pages_through_all_ids_in_document_id_order(
    search_index: InMemorySearchIndex,
) -> None:
    for document_id in ["d3", "d1", "d5", "d2", "d4"]:
        search_index.seed(document_id, doc())

    collected: list[str] = []
    after = None
    while page := search_index.search_document_ids(DocumentFilter(), page_size=2, after=after):
        collected += page
        after = page[-1]

    assert collected == ["d1", "d2", "d3", "d4", "d5"]


def test_count_existing_ids_counts_distinct_searchable_ids(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.seed("a", doc())
    search_index.seed("b", doc())
    assert search_index.count_existing_ids(["a", "b", "x", "a"]) == 2


# --- delete_by_query ---


def test_delete_by_query_deletes_matching_documents_visible_at_search_time(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.seed("a", doc("s1"))
    search_index.seed("b", doc("s1"))
    search_index.seed("c", doc("s2"))

    result = search_index.delete_by_query(DocumentFilter(source_id="s1"))

    assert result == DeleteByQueryResult(deleted=2, version_conflicts=0, failure_count=0)
    assert search_index.document_ids() == ["c"]


def test_delete_by_query_skips_documents_that_changed_since_the_search_and_reports_conflicts(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.seed("a", doc("s1"))
    search_index.seed("b", doc("s1"))
    search_index.seed("a", doc("s1", title="updated after refresh"), searchable=False)

    result = search_index.delete_by_query(DocumentFilter(source_id="s1"))

    assert result == DeleteByQueryResult(deleted=1, version_conflicts=1, failure_count=0)
    assert search_index.document_ids() == ["a"]
    # refresh 後の再実行で収束する(arch 9.14)。
    search_index.refresh()
    assert search_index.delete_by_query(DocumentFilter(source_id="s1")).deleted == 1
    assert search_index.document_ids() == []


def test_delete_by_query_counts_a_document_removed_by_another_writer_as_a_conflict(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.seed("a", doc("s1"))
    search_index.seed("b", doc("s1"))
    search_index.seed_removal("a")  # 検索時点では見えていたが、実行時には存在しない

    result = search_index.delete_by_query(DocumentFilter(source_id="s1"))

    assert result == DeleteByQueryResult(deleted=1, version_conflicts=1, failure_count=0)
    assert search_index.document_ids() == []


def test_delete_by_query_ignores_documents_not_yet_refreshed(
    search_index: InMemorySearchIndex,
) -> None:
    search_index.seed("a", doc("s1"), searchable=False)
    assert search_index.delete_by_query(DocumentFilter(source_id="s1")).deleted == 0
    assert search_index.document_ids() == ["a"]


def test_delete_by_query_requires_a_source(search_index: InMemorySearchIndex) -> None:
    with pytest.raises(ValueError, match="source_id"):
        search_index.delete_by_query(DocumentFilter())


# --- フック・応答の差し替え ---


def test_hook_between_read_and_write_forces_a_conflict(search_index: InMemorySearchIndex) -> None:
    """読み(GET)と書き込み(PUT)の間に別の書き込みを差し込む(C-18〜C-20、D-87)。"""
    search_index.create("d1", doc(title="a"))
    read = search_index.fetch("d1")
    search_index.behavior.before(ops.REPLACE, lambda: search_index.seed("d1", doc(title="other")))

    outcome = search_index.replace_if_unchanged(
        "d1", doc(title="mine"), seq_no=read.seq_no, primary_term=read.primary_term
    )

    assert outcome == Conflict()
    assert search_index.source_of("d1")["title"] == "other"


def test_hook_runs_once_and_does_not_reenter(search_index: InMemorySearchIndex) -> None:
    runs: list[str] = []

    def hook() -> None:
        runs.append("hook")
        search_index.fetch("d1")  # 同じ操作を呼んでも再入しない

    search_index.behavior.before(ops.FETCH, hook)
    search_index.fetch("d1")
    search_index.fetch("d1")

    assert runs == ["hook"]


def test_injected_conflicts_repeat_the_given_number_of_times_then_real_behavior_resumes(
    search_index: InMemorySearchIndex,
) -> None:
    """409 を読み直しの上限回数まで返し続ける(C-18b、C-19b)。"""
    search_index.create("d1", doc())
    search_index.behavior.inject(ops.REPLACE, Conflict(), times=3)
    read = search_index.fetch("d1")

    outcomes = [
        search_index.replace_if_unchanged(
            "d1", doc(), seq_no=read.seq_no, primary_term=read.primary_term
        )
        for _ in range(4)
    ]

    assert outcomes[:3] == [Conflict()] * 3
    assert isinstance(outcomes[3], Written)


def test_injection_with_times_none_never_ends_and_leaves_state_unchanged(
    search_index: InMemorySearchIndex,
) -> None:
    """`_count` が 0 にならない応答を返し続ける(D-90(c))。"""
    search_index.behavior.inject(ops.COUNT, 5, times=None)
    assert [search_index.count(DocumentFilter()) for _ in range(10)] == [5] * 10


def test_injected_exception_is_raised(search_index: InMemorySearchIndex) -> None:
    search_index.behavior.inject(ops.CREATE, OpenSearchUnavailableError("http_503"))
    with pytest.raises(OpenSearchUnavailableError):
        search_index.create("d1", doc())
    assert search_index.document_ids() == []


def test_injected_fetch_result_can_be_none(search_index: InMemorySearchIndex) -> None:
    search_index.seed("d1", doc())
    search_index.behavior.inject(ops.FETCH, None)
    assert search_index.fetch("d1") is None
    assert search_index.fetch("d1") is not None


def test_injected_delete_by_query_result_reports_version_conflicts(
    search_index: InMemorySearchIndex,
) -> None:
    """D-90(a)。"""
    search_index.seed("a", doc("s1"))
    search_index.behavior.inject(
        ops.DELETE_BY_QUERY, DeleteByQueryResult(deleted=0, version_conflicts=2, failure_count=0)
    )
    result = search_index.delete_by_query(DocumentFilter(source_id="s1"))
    assert result.version_conflicts == 2
    assert search_index.document_ids() == ["a"]


def test_write_calls_record_only_write_operations(search_index: InMemorySearchIndex) -> None:
    search_index.fetch("d1")
    search_index.count(DocumentFilter())
    assert search_index.write_calls() == []

    search_index.create("d1", doc())
    search_index.raise_last_seen_at("d1", T3)
    assert search_index.write_calls() == [ops.CREATE, ops.RAISE_LAST_SEEN_AT]


def test_hook_before_delete_can_make_the_delete_conflict(search_index: InMemorySearchIndex) -> None:
    search_index.create("d1", doc(title="a"))
    read = search_index.fetch("d1")
    search_index.behavior.before(ops.DELETE, lambda: search_index.seed("d1", doc(title="other")))

    outcome = search_index.delete_if_unchanged(
        "d1", seq_no=read.seq_no, primary_term=read.primary_term
    )

    assert outcome == Conflict()
    assert search_index.source_of("d1")["title"] == "other"


def test_hook_for_a_key_waits_for_a_call_with_that_key(search_index: InMemorySearchIndex) -> None:
    runs: list[str] = []
    search_index.behavior.before(ops.FETCH, lambda: runs.append("d2-hook"), key="d2")

    search_index.fetch("d1")
    search_index.count(DocumentFilter())  # キーなしの操作でも発火しない
    assert runs == []

    search_index.fetch("d2")
    search_index.fetch("d2")
    assert runs == ["d2-hook"]


def test_injection_for_a_key_does_not_affect_other_keys(search_index: InMemorySearchIndex) -> None:
    search_index.seed("d1", doc())
    search_index.seed("d2", doc())
    search_index.behavior.inject(ops.FETCH, None, key="d2")

    assert search_index.fetch("d1") is not None
    assert search_index.fetch("d2") is None  # 一致するまで残っていた差し替えを消費する
    assert search_index.fetch("d2") is not None


def test_hooks_are_consumed_in_registration_order_and_before_injections(
    search_index: InMemorySearchIndex,
) -> None:
    events: list[str] = []
    search_index.behavior.before(ops.COUNT, lambda: events.append("hook-1"))
    search_index.behavior.before(ops.COUNT, lambda: events.append("hook-2"))
    search_index.behavior.inject(ops.COUNT, 7, times=None)

    assert search_index.count(DocumentFilter()) == 7
    assert events == ["hook-1"]
    assert search_index.count(DocumentFilter()) == 7
    assert events == ["hook-1", "hook-2"]


def test_hook_changes_are_visible_to_the_injected_call_that_follows(
    search_index: InMemorySearchIndex,
) -> None:
    """フック → 差し替えの順。差し替えた呼び出しの前に、フックが差し込んだ状態は反映済み。"""
    search_index.behavior.before(ops.FETCH, lambda: search_index.seed("d1", doc()), key="d1")
    search_index.behavior.inject(ops.FETCH, "injected", key="d1")

    assert search_index.fetch("d1") == "injected"
    assert search_index.document_ids() == ["d1"]


def test_calls_record_the_operation_and_the_key(search_index: InMemorySearchIndex) -> None:
    search_index.fetch("d1")
    search_index.count(DocumentFilter())
    search_index.create("d2", doc())

    assert search_index.behavior.calls == [
        Call(ops.FETCH, "d1"),
        Call(ops.COUNT, None),
        Call(ops.CREATE, "d2"),
    ]
