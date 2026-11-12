"""`last-seen` 部分更新(arch 5章、api 4.2)。"""

from datetime import timedelta, timezone

import pytest

from loreley_indexer.common.errors import (
    AdmissionRejectedError,
    CrawlAlreadyClosedError,
    CrawlFinishedError,
    CrawlNotStartedError,
    CrawlSourceMismatchError,
    CrawlStartedAtMismatchError,
    UnavailableError,
)
from loreley_indexer.crawl_runs.lifecycle import DeletionStatus
from loreley_indexer.documents import LastSeenEntry, LastSeenResult, LastSeenUpdater
from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    OpenSearchUnavailableError,
    OpenSearchUnexpectedResponseError,
    Rejected,
)
from tests.crawl_runs.factories import (
    CRAWL_ID,
    CRAWL_STARTED_AT,
    CRAWL_STARTED_AT_TEXT,
    SOURCE_ID,
    make_result,
    seed_result,
)
from tests.documents.factories import id_of, make_context, seed_lock
from tests.fakes import in_memory_search_index as ops
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore

pytestmark = pytest.mark.usefixtures("running_crawl")


def seed_document(
    search_index: InMemorySearchIndex, external_id: str, last_seen_at: str | None
) -> str:
    document_id = id_of(external_id)
    source = {"document_id": document_id, "source_id": SOURCE_ID, "title": "keep me"}
    if last_seen_at is not None:
        source["last_seen_at"] = last_seen_at
    search_index.seed(document_id, source)
    return document_id


# --- 結果区分(C-21、E-20) ---


def test_newer_value_is_written_and_only_last_seen_at_changes(
    last_seen_updater: LastSeenUpdater, search_index: InMemorySearchIndex
) -> None:
    """C-21(a)。"""
    document_id = seed_document(search_index, "a.txt", "2026-11-01T00:00:00.000Z")

    entries = last_seen_updater.update(make_context(), [document_id])

    assert entries == [LastSeenEntry(document_id, LastSeenResult.UPDATED)]
    assert search_index.source_of(document_id) == {
        "document_id": document_id,
        "source_id": SOURCE_ID,
        "title": "keep me",
        "last_seen_at": CRAWL_STARTED_AT_TEXT,
    }


@pytest.mark.parametrize("current", [CRAWL_STARTED_AT_TEXT, "2026-11-10T00:00:00.000Z"])
def test_equal_or_newer_current_value_is_left_alone(
    last_seen_updater: LastSeenUpdater, search_index: InMemorySearchIndex, current: str
) -> None:
    """C-21(b)、C-4: 現在値以上は noop(書かない)。古い時刻で戻さない。"""
    document_id = seed_document(search_index, "a.txt", current)

    entries = last_seen_updater.update(make_context(), [document_id])

    assert entries == [LastSeenEntry(document_id, LastSeenResult.UNCHANGED)]
    assert search_index.source_of(document_id)["last_seen_at"] == current


def test_missing_document_is_not_created(
    last_seen_updater: LastSeenUpdater, search_index: InMemorySearchIndex
) -> None:
    """C-21(c)、E-20(a): 文書がなければ何もしない(upsert しない)。新規文書では正常。"""
    document_id = id_of("new.txt")

    entries = last_seen_updater.update(make_context(), [document_id])

    assert entries == [LastSeenEntry(document_id, LastSeenResult.NOT_FOUND)]
    assert search_index.document_ids() == []


def test_update_conflict_beyond_retry_on_conflict_is_a_retryable_document_failure(
    last_seen_updater: LastSeenUpdater, search_index: InMemorySearchIndex
) -> None:
    """C-21(d)、E-20(b): `update_conflict`。ほかの文書は処理される。"""
    conflicted = seed_document(search_index, "a.txt", None)
    healthy = seed_document(search_index, "b.txt", None)
    search_index.behavior.inject(ops.RAISE_LAST_SEEN_AT, Conflict(), key=conflicted)

    entries = last_seen_updater.update(make_context(), [conflicted, healthy])

    assert [entry.result for entry in entries] == [
        LastSeenResult.UPDATE_CONFLICT,
        LastSeenResult.UPDATED,
    ]


def test_missing_index_is_a_whole_index_failure_that_propagates(
    last_seen_updater: LastSeenUpdater, search_index: InMemorySearchIndex
) -> None:
    """E-20(c): `index_not_found_exception` などは、文書単位ではなくリクエスト全体の異常にする。"""
    search_index.behavior.inject(
        ops.RAISE_LAST_SEEN_AT, OpenSearchUnavailableError("index_not_found_exception")
    )

    with pytest.raises(UnavailableError):
        last_seen_updater.update(make_context(), [id_of("a.txt")])


def test_rejected_update_is_an_unexpected_response_not_a_document_result(
    last_seen_updater: LastSeenUpdater, search_index: InMemorySearchIndex
) -> None:
    """固定スクリプトの Update が 4xx で拒否されるのは、Indexer 側の異常(api では 500)。"""
    document_id = seed_document(search_index, "a.txt", None)
    search_index.behavior.inject(ops.RAISE_LAST_SEEN_AT, Rejected("script_exception"))

    with pytest.raises(OpenSearchUnexpectedResponseError):
        last_seen_updater.update(make_context(), [document_id])


def test_results_keep_the_input_order(
    last_seen_updater: LastSeenUpdater, search_index: InMemorySearchIndex
) -> None:
    ids = [seed_document(search_index, name, None) for name in ("c.txt", "a.txt", "b.txt")]
    ids.insert(1, id_of("missing.txt"))

    entries = last_seen_updater.update(make_context(), ids)

    assert [entry.document_id for entry in entries] == ids
    assert [entry.result for entry in entries] == [
        LastSeenResult.UPDATED,
        LastSeenResult.NOT_FOUND,
        LastSeenResult.UPDATED,
        LastSeenResult.UPDATED,
    ]


def test_empty_list_returns_no_results(last_seen_updater: LastSeenUpdater) -> None:
    assert last_seen_updater.update(make_context(), []) == []


def test_rewrite_mode_does_not_affect_last_seen(
    last_seen_updater: LastSeenUpdater,
    deletions_store: InMemoryStore,
    search_index: InMemorySearchIndex,
) -> None:
    """C-27: `last_seen_at` の部分更新は、再書き込みモードに影響されない。"""
    seed_result(deletions_store, make_result(rewrite_mode=True))
    document_id = seed_document(search_index, "a.txt", CRAWL_STARTED_AT_TEXT)

    entries = last_seen_updater.update(make_context(), [document_id])

    assert entries[0].result is LastSeenResult.UNCHANGED


def test_crawl_started_at_in_another_notation_is_written_as_utc_milliseconds(
    last_seen_updater: LastSeenUpdater, search_index: InMemorySearchIndex
) -> None:
    """C-26: オフセット付きの表記でも、UTC・ミリ秒で保存し、Instant で比較する。"""
    jst = timezone(timedelta(hours=9))
    # 文字列では新しく見える(`09:30+09:00` > `01:00Z`)が、時刻は 00:30Z で、より前。
    document_id = seed_document(search_index, "a.txt", "2026-11-09T09:30:00+09:00")

    entries = last_seen_updater.update(
        make_context(crawl_started_at=CRAWL_STARTED_AT.astimezone(jst)), [document_id]
    )

    assert entries[0].result is LastSeenResult.UPDATED
    assert search_index.source_of(document_id)["last_seen_at"] == CRAWL_STARTED_AT_TEXT


# --- 受理条件(リクエストの先頭で 1 回。拒否では 1 件も書かない) ---


@pytest.mark.parametrize(
    ("result_change", "error"),
    [
        ("no_result", CrawlNotStartedError),
        ({"source_id": "other"}, CrawlSourceMismatchError),
        (
            {"crawl_started_at": CRAWL_STARTED_AT + timedelta(seconds=1)},
            CrawlStartedAtMismatchError,
        ),
        ({"status": DeletionStatus.DISCARDED}, CrawlAlreadyClosedError),
        ({"finish_received_at": DEFAULT_NOW}, CrawlFinishedError),
    ],
)
def test_rejected_admission_writes_nothing(
    last_seen_updater: LastSeenUpdater,
    deletions_store: InMemoryStore,
    search_index: InMemorySearchIndex,
    result_change: object,
    error: type[AdmissionRejectedError],
) -> None:
    """D-77、D-78、D-81、D-82: 5 種の拒否は例外で、1 件も書かない。"""
    if result_change == "no_result":
        deletions_store.delete(f"deletion_result-{CRAWL_ID}")
    else:
        seed_result(deletions_store, make_result(**result_change))  # type: ignore[arg-type]
    document_id = seed_document(search_index, "a.txt", None)

    with pytest.raises(error):
        last_seen_updater.update(make_context(), [document_id])

    assert search_index.write_calls() == []


# --- ロック所有確認(L-5、案5) ---


def test_lock_not_owned_writes_nothing(
    last_seen_updater: LastSeenUpdater,
    jobs_store: InMemoryStore,
    search_index: InMemorySearchIndex,
) -> None:
    seed_lock(jobs_store, owner="crawler-2")
    document_id = seed_document(search_index, "a.txt", None)

    entries = last_seen_updater.update(make_context(), [document_id])

    assert entries == [LastSeenEntry(document_id, LastSeenResult.LOCK_NOT_OWNED)]
    assert search_index.write_calls() == []


def test_losing_the_lock_mid_request_marks_the_rest_not_owned(
    last_seen_updater: LastSeenUpdater, search_index: InMemorySearchIndex, clock: FixedClock
) -> None:
    ids = [seed_document(search_index, f"d{n}.txt", None) for n in range(4)]
    search_index.behavior.before(
        ops.RAISE_LAST_SEEN_AT, lambda: clock.advance(seconds=7200), key=ids[1]
    )

    entries = last_seen_updater.update(make_context(), ids)

    assert [entry.result for entry in entries] == [
        LastSeenResult.UPDATED,
        LastSeenResult.UPDATED,
        LastSeenResult.LOCK_NOT_OWNED,
        LastSeenResult.LOCK_NOT_OWNED,
    ]
    assert search_index.source_of(ids[2]).get("last_seen_at") is None


def test_once_the_lock_is_lost_a_later_reappearance_does_not_resume_the_request(
    last_seen_updater: LastSeenUpdater, jobs_store: InMemoryStore, search_index: InMemorySearchIndex
) -> None:
    """案5: 最初の失敗以降は、ロックが戻っても未処理の文書は書かない。"""
    ids = [seed_document(search_index, f"d{n}.txt", None) for n in range(4)]
    lock_id = f"lock-{SOURCE_ID}"
    lock = jobs_store.body_of(lock_id)
    assert lock is not None
    for hook in (
        lambda: None,
        lambda: None,
        lambda: jobs_store.delete(lock_id),
        lambda: jobs_store.seed(lock_id, lock),
    ):
        jobs_store.behavior.before("fetch", hook, key=lock_id)

    entries = last_seen_updater.update(make_context(), ids)

    assert [entry.result for entry in entries] == [
        LastSeenResult.UPDATED,
        LastSeenResult.UPDATED,
        LastSeenResult.LOCK_NOT_OWNED,
        LastSeenResult.LOCK_NOT_OWNED,
    ]


# --- 入力の防御的な検査(HTTP の 400 は api 層) ---


def test_too_many_ids_are_rejected_before_anything_is_read(
    last_seen_updater: LastSeenUpdater,
    deletions_store: InMemoryStore,
    search_index: InMemorySearchIndex,
) -> None:
    """設定の上限(テストでは 5 件)を超える件数は ValueError。"""
    ids = [id_of(f"d{n}.txt") for n in range(6)]

    with pytest.raises(ValueError, match="too many"):
        last_seen_updater.update(make_context(), ids)

    assert search_index.behavior.calls == []
    assert deletions_store.behavior.calls == []


@pytest.mark.parametrize("invalid", ["abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65])
def test_malformed_document_ids_are_rejected_without_echoing_them(
    last_seen_updater: LastSeenUpdater, search_index: InMemorySearchIndex, invalid: str
) -> None:
    with pytest.raises(ValueError, match="64 lowercase hex") as exc_info:
        last_seen_updater.update(make_context(), [id_of("ok.txt"), invalid])

    assert invalid not in str(exc_info.value)
    assert search_index.behavior.calls == []


def test_empty_document_id_is_rejected_with_the_fixed_message(
    last_seen_updater: LastSeenUpdater, search_index: InMemorySearchIndex
) -> None:
    """空文字列はどんなメッセージにも含まれるため、入力値を含まないことは文言の完全一致で確かめる。"""
    with pytest.raises(ValueError) as exc_info:
        last_seen_updater.update(make_context(), [""])

    assert str(exc_info.value) == "document_id must be 64 lowercase hex characters"
    assert search_index.behavior.calls == []


def test_ids_at_the_limit_are_accepted(last_seen_updater: LastSeenUpdater) -> None:
    ids = [id_of(f"d{n}.txt") for n in range(5)]

    assert len(last_seen_updater.update(make_context(), ids)) == 5
