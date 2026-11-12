"""バッチ登録の分岐と結果区分(arch 4.3、5章、8章。api 4.3)。

競合は test_registration_conflicts.py。
"""

import unicodedata
from dataclasses import replace
from datetime import timedelta, timezone
from typing import Any

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
from loreley_indexer.documents import (
    Change,
    DocumentFailed,
    DocumentInput,
    DocumentRegistered,
    DocumentRegistrar,
    FailureType,
    RegistrationConfig,
)
from loreley_indexer.documents.extraction import ExtractedText, ExtractionConfig, TextExtractor
from loreley_indexer.documents.summarization import SummaryRequestQueue
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
from tests.documents.conftest import MAX_CONTENT_BYTES, MAX_RAW_BYTES
from tests.documents.factories import (
    SOURCE_UPDATED_AT,
    id_of,
    make_context,
    make_document,
    register_one,
    seed_lock,
    stored_document,
)
from tests.fakes import in_memory_search_index as ops
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore

pytestmark = pytest.mark.usefixtures("running_crawl")


def extract(document: DocumentInput) -> ExtractedText:
    result = TextExtractor(ExtractionConfig(MAX_CONTENT_BYTES)).extract(
        document.raw_content, document.mime_type
    )
    assert isinstance(result, ExtractedText)
    return result


# --- 受理条件(リクエストの先頭で 1 回。拒否では 1 件も書かない) ---


def reject_with_no_result(deletions_store: InMemoryStore) -> None:
    deletions_store.delete(f"deletion_result-{CRAWL_ID}")


def reject_with_other_source(deletions_store: InMemoryStore) -> None:
    seed_result(deletions_store, make_result(source_id="other"))


def reject_with_other_started_at(deletions_store: InMemoryStore) -> None:
    seed_result(
        deletions_store, make_result(crawl_started_at=CRAWL_STARTED_AT + timedelta(seconds=1))
    )


def reject_with_closed_result(deletions_store: InMemoryStore) -> None:
    seed_result(deletions_store, make_result(status=DeletionStatus.FAILED))


def reject_with_finish_received(deletions_store: InMemoryStore) -> None:
    seed_result(deletions_store, make_result(finish_received_at=DEFAULT_NOW))


@pytest.mark.parametrize(
    ("break_admission", "error"),
    [
        (reject_with_no_result, CrawlNotStartedError),
        (reject_with_other_source, CrawlSourceMismatchError),
        (reject_with_other_started_at, CrawlStartedAtMismatchError),
        (reject_with_closed_result, CrawlAlreadyClosedError),
        (reject_with_finish_received, CrawlFinishedError),
    ],
)
def test_rejected_admission_writes_nothing_and_touches_no_document(
    registrar: DocumentRegistrar,
    deletions_store: InMemoryStore,
    search_index: InMemorySearchIndex,
    break_admission,
    error: type[AdmissionRejectedError],
) -> None:
    """D-77、D-78、D-81、D-82: 5 種の拒否は例外で、1 件も処理しない(fetch も書き込みもしない)。"""
    break_admission(deletions_store)

    with pytest.raises(error):
        registrar.register(make_context(), [make_document("a.txt"), make_document("b.txt")])

    assert search_index.write_calls() == []
    assert search_index.behavior.calls == []


def test_unavailable_admission_lookup_propagates_without_writing(
    registrar: DocumentRegistrar,
    deletions_store: InMemoryStore,
    search_index: InMemorySearchIndex,
) -> None:
    deletions_store.behavior.inject("fetch", OpenSearchUnavailableError("http_503"))

    with pytest.raises(UnavailableError):
        registrar.register(make_context(), [make_document()])

    assert search_index.write_calls() == []


def test_invalid_external_id_is_rejected_before_any_write(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    with pytest.raises(ValueError, match="NUL"):
        registrar.register(make_context(), [make_document("a.txt"), make_document("b\x00.txt")])

    assert search_index.behavior.calls == []


# --- 新規・変更なし・更新(C-17、C-10a) ---


def test_new_document_is_created_with_every_field(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """C-17(a): 要約が無効なら `summary_status=disabled` で、`summary` は書かない。"""
    document = make_document(url="https://wiki.example/a", path="docs/a")

    outcome = register_one(registrar, document)

    extracted = extract(document)
    assert outcome == DocumentRegistered(
        external_id="docs/a.txt",
        document_id=id_of(document),
        change=Change.CREATED,
        extract_failed=False,
    )
    assert stored_document(search_index, document) == {
        "document_id": id_of(document),
        "source_id": SOURCE_ID,
        "external_id": "docs/a.txt",
        "title": "A",
        "url": "https://wiki.example/a",
        "path": "docs/a",
        "mime_type": "text/plain",
        "size": len(document.raw_content),
        "source_updated_at": "2026-11-08T12:00:00.000Z",
        "content": extracted.text,
        "content_hash": document.content_hash,
        "text_hash": extracted.text_hash,
        "truncated": False,
        "index_status": "indexed",
        "summary_status": "disabled",
        "indexed_at": "2026-11-11T00:00:00.000Z",
        "last_seen_at": CRAWL_STARTED_AT_TEXT,
    }
    assert search_index.write_calls() == [ops.CREATE]


def test_results_keep_the_input_order_and_echo_the_sent_external_id(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    nfd_id = unicodedata.normalize("NFD", "資料/がぎ.txt")
    documents = [make_document(nfd_id), make_document("b.txt"), make_document("a.txt")]

    outcomes = registrar.register(make_context(), documents)

    assert [outcome.external_id for outcome in outcomes] == [nfd_id, "b.txt", "a.txt"]
    assert [outcome.document_id for outcome in outcomes] == [id_of(d) for d in documents]
    stored = search_index.source_of(outcomes[0].document_id)
    assert stored is not None
    assert stored["external_id"] == unicodedata.normalize("NFC", nfd_id)


def test_same_external_id_twice_in_a_batch_is_created_then_unchanged(
    registrar: DocumentRegistrar,
) -> None:
    outcomes = registrar.register(make_context(), [make_document(), make_document()])

    assert [outcome.change for outcome in outcomes] == [Change.CREATED, Change.UNCHANGED]


def test_unchanged_document_is_not_written_again(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """C-10a: すべて同じなら PUT せず(`_seq_no` が変わらない)、補完の Update もしない。"""
    document = make_document()
    register_one(registrar, document)
    version = search_index.fetch(id_of(document))

    outcome = register_one(registrar, document)

    assert outcome == DocumentRegistered("docs/a.txt", id_of(document), Change.UNCHANGED, False)
    assert search_index.fetch(id_of(document)) == version
    assert search_index.write_calls() == [ops.CREATE]


def test_changed_body_is_replaced_and_updated(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """C-17(b)。"""
    register_one(registrar, make_document(text="old text"))
    changed = make_document(text="new text")

    outcome = register_one(registrar, changed)

    assert outcome.change is Change.UPDATED
    stored = stored_document(search_index, changed)
    assert stored["content"] == "new text"
    assert stored["content_hash"] == changed.content_hash
    assert stored["text_hash"] == extract(changed).text_hash
    assert search_index.write_calls() == [ops.CREATE, ops.REPLACE]


@pytest.mark.parametrize(
    "metadata_change",
    [
        {"title": "B"},
        {"source_updated_at": SOURCE_UPDATED_AT + timedelta(hours=1)},
        {"mime_type": "text/markdown"},
        {"url": "https://wiki.example/a"},
        {"path": "docs/a"},
        {"size": 999},
    ],
    ids=["title", "source_updated_at", "mime_type", "url", "path", "size"],
)
def test_metadata_only_change_is_replaced_and_updated(
    registrar: DocumentRegistrar,
    search_index: InMemorySearchIndex,
    metadata_change: dict[str, Any],
) -> None:
    """C-17(c): 変更判定の 6 つのメタデータのどれが変わっても、全文書き込みする。"""
    document = make_document()
    register_one(registrar, document)

    outcome = register_one(registrar, replace(document, **metadata_change))

    assert outcome.change is Change.UPDATED
    name, value = next(iter(metadata_change.items()))
    stored_value = stored_document(search_index, document)[name]
    expected = "2026-11-08T13:00:00.000Z" if name == "source_updated_at" else value
    assert stored_value == expected


def test_source_updated_at_is_compared_after_normalization(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """表記が違うだけの同じ時刻(JST のオフセット)は、変更なしとして扱う(api 3.6)。"""
    document = make_document()
    register_one(registrar, document)
    same_instant = SOURCE_UPDATED_AT.astimezone(timezone(timedelta(hours=9)))

    outcome = register_one(registrar, replace(document, source_updated_at=same_instant))

    assert outcome.change is Change.UNCHANGED
    assert search_index.write_calls() == [ops.CREATE]


def test_changed_text_hash_with_the_same_content_hash_is_updated(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """C-12: 原本が同じで抽出結果だけが変わる(抽出ロジックの変更)。本文とハッシュが更新される。"""
    document = make_document()
    register_one(registrar, document)
    stored = stored_document(search_index, document)
    search_index.seed(
        id_of(document), {**stored, "content": "old extraction", "text_hash": "0" * 64}
    )

    outcome = register_one(registrar, document)

    assert outcome.change is Change.UPDATED
    refreshed = stored_document(search_index, document)
    assert refreshed["text_hash"] == extract(document).text_hash
    assert refreshed["content"] == extract(document).text


def test_changed_text_hash_with_the_same_content_hash_resets_the_summary(
    summary_registrar: DocumentRegistrar,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
) -> None:
    """C-3、C-12: 原本が同じでも抽出結果(`text_hash`)が変われば、要約は引き継がず `pending` に戻す。

    要約は本文から作るので、`content_hash` だけが同じでも本文が違えば古い要約は使えない。
    """
    document = make_document()
    register_one(summary_registrar, document)
    summary_requests.take()
    stored = stored_document(search_index, document)
    search_index.seed(
        id_of(document),
        {
            **stored,
            "text_hash": "0" * 64,
            "summary": "old",
            "summary_status": "generated",
            "summary_model": "m",
        },
    )

    outcome = register_one(summary_registrar, document)

    assert outcome.change is Change.UPDATED
    refreshed = stored_document(search_index, document)
    assert refreshed["text_hash"] == extract(document).text_hash
    assert refreshed["summary_status"] == "pending"
    assert "summary" not in refreshed
    assert "summary_model" not in refreshed
    assert summary_requests.take() == id_of(document)


def test_content_over_the_limit_is_truncated_and_flagged(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """E-6: 抽出後の本文が上限を超えたら、上限まで索引化して `truncated=true`。"""
    document = make_document(text="a" * (MAX_CONTENT_BYTES + 50))

    outcome = register_one(registrar, document)

    assert outcome.change is Change.CREATED
    stored = stored_document(search_index, document)
    assert stored["truncated"] is True
    assert len(stored["content"].encode("utf-8")) == MAX_CONTENT_BYTES


# --- last_seen_at(C-4、C-10b、C-26) ---


def test_replace_never_moves_last_seen_at_backwards(
    registrar: DocumentRegistrar,
    deletions_store: InMemoryStore,
    search_index: InMemorySearchIndex,
) -> None:
    """C-4: 古い `crawl_started_at` の全文書き込みでも、既存の `last_seen_at` は新しいまま。"""
    document = make_document(text="old text")
    register_one(registrar, document)
    stored = stored_document(search_index, document)
    search_index.seed(id_of(document), {**stored, "last_seen_at": "2026-11-10T00:00:00.000Z"})

    outcome = register_one(registrar, make_document(text="new text"))

    assert outcome.change is Change.UPDATED
    assert stored_document(search_index, document)["last_seen_at"] == "2026-11-10T00:00:00.000Z"


def test_last_seen_at_takes_the_later_instant_not_the_later_string(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """C-26: `+09:00` 表記の 00:30Z は、文字列では大きいが `crawl_started_at`(01:00Z)より前。"""
    document = make_document(text="old text")
    register_one(registrar, document)
    stored = stored_document(search_index, document)
    search_index.seed(id_of(document), {**stored, "last_seen_at": "2026-11-09T09:30:00+09:00"})

    register_one(registrar, make_document(text="new text"))

    assert stored_document(search_index, document)["last_seen_at"] == CRAWL_STARTED_AT_TEXT


def test_crawl_started_at_in_another_notation_is_stored_as_utc_milliseconds(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """C-26: オフセット付きの `crawl_started_at` でも、UTC・ミリ秒に正規化して保存する。"""
    jst = timezone(timedelta(hours=9))

    register_one(registrar, make_document(), crawl_started_at=CRAWL_STARTED_AT.astimezone(jst))

    assert stored_document(search_index, "docs/a.txt")["last_seen_at"] == CRAWL_STARTED_AT_TEXT


def test_microsecond_crawl_started_at_does_not_cause_a_needless_completion_update(
    registrar: DocumentRegistrar,
    deletions_store: InMemoryStore,
    search_index: InMemorySearchIndex,
) -> None:
    """保存はミリ秒精度。マイクロ秒を持つ入力でも、書いた直後の値を古いと見なさない。"""
    started_at = CRAWL_STARTED_AT + timedelta(microseconds=123_456)
    seed_result(deletions_store, make_result(crawl_started_at=started_at))
    document = make_document()
    register_one(registrar, document, crawl_started_at=started_at)
    assert stored_document(search_index, document)["last_seen_at"] == "2026-11-09T01:00:00.123Z"

    outcome = register_one(registrar, document, crawl_started_at=started_at)

    assert outcome.change is Change.UNCHANGED
    assert search_index.write_calls() == [ops.CREATE]  # 補完の Update を送らない


def test_unchanged_document_with_an_old_last_seen_at_is_completed_by_an_update_only(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """C-10b: 列挙時の部分更新が失敗・省略された変更なしの文書は、PUT せず Update だけで補う。"""
    document = make_document()
    register_one(registrar, document)
    stored = stored_document(search_index, document)
    search_index.seed(id_of(document), {**stored, "last_seen_at": "2026-11-01T00:00:00.000Z"})
    write_calls_before = search_index.write_calls()

    outcome = register_one(registrar, document)

    assert outcome.change is Change.UNCHANGED
    assert search_index.write_calls()[len(write_calls_before) :] == [ops.RAISE_LAST_SEEN_AT]
    assert stored_document(search_index, document) == {
        **stored,
        "last_seen_at": CRAWL_STARTED_AT_TEXT,
    }


def test_update_conflict_on_the_completion_is_a_retryable_document_failure(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """C-10b + K51: 補完の Update が `retry_on_conflict` を超えて 409 なら `update_conflict`。"""
    document = make_document()
    register_one(registrar, document)
    stored = stored_document(search_index, document)
    search_index.seed(id_of(document), {**stored, "last_seen_at": "2026-11-01T00:00:00.000Z"})
    search_index.behavior.inject(ops.RAISE_LAST_SEEN_AT, Conflict())

    outcome = register_one(registrar, document)

    assert isinstance(outcome, DocumentFailed)
    assert outcome.failure_type is FailureType.UPDATE_CONFLICT


# --- 再書き込みモード(C-22、C-27) ---


def test_rewrite_mode_writes_even_an_unchanged_document(
    registrar: DocumentRegistrar,
    deletions_store: InMemoryStore,
    search_index: InMemorySearchIndex,
) -> None:
    """C-22(b-1)、C-27(a): 変更なしの判定をせず全文書き込みし、`change` は `updated`。"""
    document = make_document()
    register_one(registrar, document)
    seed_result(deletions_store, make_result(rewrite_mode=True))

    outcome = register_one(registrar, document)

    assert outcome.change is Change.UPDATED
    assert search_index.write_calls() == [ops.CREATE, ops.REPLACE]


def test_rewrite_mode_applies_to_every_batch_of_the_crawl(
    registrar: DocumentRegistrar,
    deletions_store: InMemoryStore,
    search_index: InMemorySearchIndex,
) -> None:
    """C-27(a): モードは受理条件の確認で取得した値で、同じクロールの複数バッチで変わらない。"""
    documents = [make_document(f"d{n}.txt") for n in range(3)]
    for document in documents:
        register_one(registrar, document)
    seed_result(deletions_store, make_result(rewrite_mode=True))

    changes = [register_one(registrar, document).change for document in documents]

    assert changes == [Change.UPDATED] * 3


def test_default_mode_leaves_unchanged_documents_alone(
    registrar: DocumentRegistrar,
    search_index: InMemorySearchIndex,
) -> None:
    """C-27(b): `rewrite_mode=false`(既定)なら、同じ文書は 2 回目に書かれない。"""
    document = make_document()
    register_one(registrar, document)

    assert register_one(registrar, document).change is Change.UNCHANGED
    assert search_index.write_calls() == [ops.CREATE]


# --- 抽出失敗(E-5、E-44、E-45、K30) ---

UNREADABLE_PDF = {"mime_type": "application/pdf", "raw_content": b"this is not a pdf"}


def test_extract_failed_document_registers_only_title_and_metadata(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """E-5、E-44: `extract_failed` は本文・`text_hash`・要約を持たず、`summary_status=disabled`。"""
    document = make_document(**UNREADABLE_PDF)

    outcome = register_one(registrar, document)

    assert outcome == DocumentRegistered("docs/a.txt", id_of(document), Change.CREATED, True)
    assert stored_document(search_index, document) == {
        "document_id": id_of(document),
        "source_id": SOURCE_ID,
        "external_id": "docs/a.txt",
        "title": "A",
        "mime_type": "application/pdf",
        "size": len(document.raw_content),
        "source_updated_at": "2026-11-08T12:00:00.000Z",
        "content_hash": document.content_hash,
        "truncated": False,
        "index_status": "extract_failed",
        "summary_status": "disabled",
        "indexed_at": "2026-11-11T00:00:00.000Z",
        "last_seen_at": CRAWL_STARTED_AT_TEXT,
    }


def test_extract_failed_document_is_not_written_again_when_nothing_changed(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """E-44: 次のクロールでも毎回再抽出されるが、内容とメタデータが同じなら書き込まれない。"""
    document = make_document(**UNREADABLE_PDF)
    register_one(registrar, document)

    outcome = register_one(registrar, document)

    assert outcome == DocumentRegistered("docs/a.txt", id_of(document), Change.UNCHANGED, True)
    assert search_index.write_calls() == [ops.CREATE]


def test_extract_failed_document_becomes_indexed_when_extraction_succeeds(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """E-44: 抽出に成功すると `indexed` になり、`content` が登録される。"""
    register_one(registrar, make_document(**UNREADABLE_PDF))
    recovered = make_document(text="readable now")

    outcome = register_one(registrar, recovered)

    assert outcome == DocumentRegistered("docs/a.txt", id_of(recovered), Change.UPDATED, False)
    stored = stored_document(search_index, recovered)
    assert stored["index_status"] == "indexed"
    assert stored["content"] == "readable now"


@pytest.mark.parametrize("summary_enabled", [False, True])
def test_indexed_document_that_fails_extraction_loses_content_and_summary(
    make_registrar,
    registration_config: RegistrationConfig,
    search_index: InMemorySearchIndex,
    summary_enabled: bool,
) -> None:
    """E-45、C-3: 文書は削除されず `extract_failed` に遷移し、旧い本文・ハッシュ・要約が消える。

    要約が有効でも `summary_status=disabled`(要約の再走査の対象外)。
    """
    registrar = make_registrar(replace(registration_config, summary_enabled=summary_enabled))
    original = make_document(text="body that was readable")
    register_one(registrar, original)
    stored = stored_document(search_index, original)
    search_index.seed(
        id_of(original),
        {**stored, "summary": "old summary", "summary_status": "generated", "summary_model": "m"},
    )
    broken = make_document(**UNREADABLE_PDF)

    outcome = register_one(registrar, broken)

    assert outcome == DocumentRegistered("docs/a.txt", id_of(broken), Change.UPDATED, True)
    refreshed = stored_document(search_index, broken)
    assert refreshed["index_status"] == "extract_failed"
    assert refreshed["summary_status"] == "disabled"
    assert refreshed["content_hash"] == broken.content_hash
    assert refreshed["last_seen_at"] == stored["last_seen_at"]
    assert refreshed["title"] == "A"
    for absent in ("content", "text_hash", "summary", "summary_model"):
        assert absent not in refreshed


# --- サイズ超過(E-30、案1) ---


@pytest.mark.parametrize(
    "oversize",
    [
        {"size": MAX_RAW_BYTES + 1},
        {"raw_content": b"x" * (MAX_RAW_BYTES + 1), "size": 10},
    ],
    ids=["declared_size", "actual_bytes"],
)
def test_oversize_original_is_a_document_failure_that_leaves_the_index_alone(
    registrar: DocumentRegistrar,
    search_index: InMemorySearchIndex,
    oversize: dict[str, Any],
) -> None:
    """E-30: 申告サイズか実際のバイト数が上限超過なら、抽出せず `oversize`。既存文書も触らない。"""
    existing = make_document("big.txt")
    register_one(registrar, existing)
    stored_before = stored_document(search_index, existing)
    calls_before = len(search_index.behavior.calls)

    outcome = register_one(registrar, make_document("big.txt", **oversize))

    assert isinstance(outcome, DocumentFailed)
    assert outcome.failure_type is FailureType.OVERSIZE
    assert search_index.behavior.calls[calls_before:] == []
    assert stored_document(search_index, existing) == stored_before


def test_oversize_does_not_stop_the_other_documents_of_the_batch(
    registrar: DocumentRegistrar,
) -> None:
    outcomes = registrar.register(
        make_context(),
        [make_document("a.txt"), make_document("big.txt", size=MAX_RAW_BYTES + 1)],
    )

    assert [type(outcome) for outcome in outcomes] == [DocumentRegistered, DocumentFailed]


def test_size_at_the_limit_is_accepted(registrar: DocumentRegistrar) -> None:
    outcome = register_one(registrar, make_document(text="x" * MAX_RAW_BYTES))

    assert isinstance(outcome, DocumentRegistered)


# --- ロック所有確認(L-5、案5) ---


@pytest.mark.parametrize(
    "lock",
    [
        {"owner": "crawler-2"},
        {"job_id": "job-other"},
        {"lease_expires_at": DEFAULT_NOW},
        {"lease_expires_at": DEFAULT_NOW - timedelta(seconds=1)},
    ],
    ids=["other_owner", "other_job", "expires_now", "expired"],
)
def test_lock_not_owned_writes_nothing(
    registrar: DocumentRegistrar,
    jobs_store: InMemoryStore,
    search_index: InMemorySearchIndex,
    lock: dict[str, Any],
) -> None:
    """L-5: 所有者・ジョブの不一致、期限切れは、書き込まず文書単位の `lock_not_owned`。"""
    seed_lock(jobs_store, **lock)

    outcomes = registrar.register(make_context(), [make_document("a.txt"), make_document("b.txt")])

    assert [o.failure_type for o in outcomes if isinstance(o, DocumentFailed)] == [
        FailureType.LOCK_NOT_OWNED
    ] * 2
    assert search_index.behavior.calls == []


def test_missing_lock_document_means_not_owned(
    registrar: DocumentRegistrar, jobs_store: InMemoryStore, search_index: InMemorySearchIndex
) -> None:
    jobs_store.delete(f"lock-{SOURCE_ID}")

    outcome = register_one(registrar, make_document())

    assert isinstance(outcome, DocumentFailed)
    assert outcome.failure_type is FailureType.LOCK_NOT_OWNED
    assert search_index.write_calls() == []


def test_losing_the_lock_mid_batch_keeps_earlier_results_and_stops_the_rest(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex, clock: FixedClock
) -> None:
    """案5: 確認済みの結果はそのまま。最初の失敗以降は未処理の文書も `lock_not_owned`(書かない)。"""
    documents = [make_document(f"d{n}.txt") for n in range(4)]
    # 2 件目を書く直前にリースが切れる。3 件目の確認で失敗する。
    search_index.behavior.before(
        ops.CREATE, lambda: clock.advance(seconds=7200), key=id_of(documents[1])
    )

    outcomes = registrar.register(make_context(), documents)

    assert [type(outcome) for outcome in outcomes] == [
        DocumentRegistered,
        DocumentRegistered,
        DocumentFailed,
        DocumentFailed,
    ]
    assert [o.failure_type for o in outcomes[2:] if isinstance(o, DocumentFailed)] == [
        FailureType.LOCK_NOT_OWNED
    ] * 2
    assert search_index.document_ids() == sorted(id_of(d) for d in documents[:2])


def test_once_the_lock_is_lost_a_later_reappearance_does_not_resume_the_batch(
    registrar: DocumentRegistrar, jobs_store: InMemoryStore, search_index: InMemorySearchIndex
) -> None:
    """案5: 最初の失敗以降は、ロックが戻っても未処理の文書は書かない(部分結果を単純に保つ)。"""
    lock_id = f"lock-{SOURCE_ID}"
    lock = jobs_store.body_of(lock_id)
    assert lock is not None
    # ロック文書の読み出し(文書ごとに 1 回)の 3 回目の直前に消し、4 回目の直前に戻す。
    for hook in (
        lambda: None,
        lambda: None,
        lambda: jobs_store.delete(lock_id),
        lambda: jobs_store.seed(lock_id, lock),
    ):
        jobs_store.behavior.before("fetch", hook, key=lock_id)

    outcomes = registrar.register(make_context(), [make_document(f"d{n}.txt") for n in range(4)])

    assert [type(outcome) for outcome in outcomes] == [
        DocumentRegistered,
        DocumentRegistered,
        DocumentFailed,
        DocumentFailed,
    ]
    assert len(search_index.document_ids()) == 2


def test_lock_is_checked_for_every_document(
    registrar: DocumentRegistrar, jobs_store: InMemoryStore
) -> None:
    registrar.register(make_context(), [make_document(f"d{n}.txt") for n in range(3)])

    lock_reads = [c for c in jobs_store.behavior.calls_of("fetch") if c.key == f"lock-{SOURCE_ID}"]
    assert len(lock_reads) == 3


def test_ownership_is_checked_before_the_size(
    registrar: DocumentRegistrar, jobs_store: InMemoryStore
) -> None:
    jobs_store.delete(f"lock-{SOURCE_ID}")

    outcome = register_one(registrar, make_document(size=MAX_RAW_BYTES + 1))

    assert isinstance(outcome, DocumentFailed)
    assert outcome.failure_type is FailureType.LOCK_NOT_OWNED


# --- UTF-8 にできない文字列(孤立サロゲート。送信時の JSON 化でバッチ全体が落ちるのを防ぐ) ---


@pytest.mark.parametrize("field", ["title", "mime_type", "path", "url"])
def test_metadata_that_cannot_be_encoded_fails_only_that_document(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex, field: str
) -> None:
    """孤立サロゲートは再送しても直らない。その文書だけ `document_rejected` にして、続行する。"""
    sentinel = "METADATA-SENTINEL"
    broken = make_document("broken.txt", **{field: f"{sentinel}\ud800"})
    fine = make_document("fine.txt")

    first, second = registrar.register(make_context(), [broken, fine])

    assert isinstance(first, DocumentFailed)
    assert first.failure_type is FailureType.DOCUMENT_REJECTED
    assert sentinel not in first.message
    assert "\ud800" not in first.message
    assert first.external_id == "broken.txt"
    assert isinstance(second, DocumentRegistered)
    assert search_index.document_ids() == [id_of(fine)]
    assert [call.key for call in search_index.behavior.calls if call.key == id_of(broken)] == []


def test_japanese_and_astral_metadata_is_accepted(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    document = make_document(
        title="日本語 😀", path="資料/日本語.txt", url="https://wiki.example/日本語"
    )

    assert isinstance(register_one(registrar, document), DocumentRegistered)
    assert stored_document(search_index, document)["title"] == "日本語 😀"


def test_oversize_is_reported_before_the_metadata_check(registrar: DocumentRegistrar) -> None:
    """サイズ確認が先(抽出に進まない文書は、メタデータの検査にも進まない)。"""
    outcome = register_one(registrar, make_document(title="\ud800", size=MAX_RAW_BYTES + 1))

    assert isinstance(outcome, DocumentFailed)
    assert outcome.failure_type is FailureType.OVERSIZE


@pytest.mark.parametrize("external_id", ["a\ud800.txt", "\udfff"])
def test_external_id_that_cannot_be_encoded_rejects_the_whole_request_before_any_write(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex, external_id: str
) -> None:
    """ID を算出できない入力は、NUL と同じくリクエスト全体の不正(api 層が 400 にする)。"""
    with pytest.raises(ValueError, match="valid Unicode") as exc_info:
        registrar.register(make_context(), [make_document("ok.txt"), make_document(external_id)])

    assert exc_info.type is ValueError
    assert search_index.behavior.calls == []


def test_source_id_that_cannot_be_encoded_rejects_the_whole_request(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    with pytest.raises(ValueError, match="valid Unicode"):
        registrar.register(make_context(source_id="src\ud800"), [make_document()])

    assert search_index.behavior.calls == []


# --- 文書固有の拒否と全体異常 ---


def test_document_rejection_fails_only_that_document(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """E-3: 文書固有の 4xx は文書単位の `document_rejected`。ほかの文書は処理される。"""
    rejected, accepted = make_document("a.txt", text="SECRET-BODY"), make_document("b.txt")
    search_index.behavior.inject(
        ops.CREATE, Rejected("mapper_parsing_exception"), key=id_of(rejected)
    )

    first, second = registrar.register(make_context(), [rejected, accepted])

    assert isinstance(first, DocumentFailed)
    assert first.failure_type is FailureType.DOCUMENT_REJECTED
    assert "mapper_parsing_exception" in first.message
    assert "SECRET-BODY" not in first.message
    assert isinstance(second, DocumentRegistered)


def test_whole_index_failure_propagates_instead_of_becoming_a_document_failure(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """E-21: OpenSearch 全体の異常(429・5xx など)はスキップにせず、リクエスト全体の 503 にする。"""
    search_index.behavior.inject(ops.FETCH, OpenSearchUnavailableError("http_503"))

    with pytest.raises(UnavailableError):
        registrar.register(make_context(), [make_document()])


def test_unexpected_rejection_of_the_last_seen_update_is_not_a_document_failure(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    document = make_document()
    register_one(registrar, document)
    stored = stored_document(search_index, document)
    search_index.seed(id_of(document), {**stored, "last_seen_at": "2026-11-01T00:00:00.000Z"})
    search_index.behavior.inject(ops.RAISE_LAST_SEEN_AT, Rejected("script_exception"))

    with pytest.raises(OpenSearchUnexpectedResponseError):
        register_one(registrar, document)


# --- 要約の依頼(M-9) ---


def test_new_document_is_pending_and_requests_a_summary_after_the_write(
    summary_registrar: DocumentRegistrar,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
) -> None:
    document = make_document()

    register_one(summary_registrar, document)

    assert stored_document(search_index, document)["summary_status"] == "pending"
    assert "summary" not in stored_document(search_index, document)
    assert summary_requests.take() == id_of(document)
    assert summary_requests.take() is None


def test_disabled_summary_never_requests_generation(
    registrar: DocumentRegistrar, summary_requests: SummaryRequestQueue
) -> None:
    register_one(registrar, make_document())

    assert len(summary_requests) == 0


def test_unchanged_document_requests_nothing(
    summary_registrar: DocumentRegistrar, summary_requests: SummaryRequestQueue
) -> None:
    document = make_document()
    register_one(summary_registrar, document)
    summary_requests.take()

    register_one(summary_registrar, document)

    assert len(summary_requests) == 0


def test_changed_body_resets_the_summary_to_pending(
    summary_registrar: DocumentRegistrar,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
) -> None:
    """C-3: 本文が変わると、`summary` を書かず `pending` に戻し、生成を依頼する。"""
    register_one(summary_registrar, make_document(text="old text"))
    stored = stored_document(search_index, "docs/a.txt")
    search_index.seed(
        id_of("docs/a.txt"),
        {**stored, "summary": "old", "summary_status": "generated", "summary_model": "m"},
    )
    summary_requests.take()

    register_one(summary_registrar, make_document(text="new text"))

    refreshed = stored_document(search_index, "docs/a.txt")
    assert refreshed["summary_status"] == "pending"
    assert "summary" not in refreshed
    assert "summary_model" not in refreshed
    assert summary_requests.take() == id_of("docs/a.txt")


def test_metadata_only_change_carries_the_generated_summary_over(
    summary_registrar: DocumentRegistrar,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
) -> None:
    """C-2: `content_hash` と `text_hash` が同じなら、要約・状態・モデルを引き継ぎ、依頼しない。"""
    document = make_document()
    register_one(summary_registrar, document)
    stored = stored_document(search_index, document)
    search_index.seed(
        id_of(document),
        {**stored, "summary": "kept", "summary_status": "generated", "summary_model": "m-1"},
    )
    summary_requests.take()

    outcome = register_one(summary_registrar, replace(document, title="B"))

    assert outcome.change is Change.UPDATED
    refreshed = stored_document(search_index, document)
    assert refreshed["title"] == "B"
    assert (refreshed["summary"], refreshed["summary_status"], refreshed["summary_model"]) == (
        "kept",
        "generated",
        "m-1",
    )
    assert len(summary_requests) == 0


def test_rewrite_mode_resets_the_summary_to_pending(
    summary_registrar: DocumentRegistrar,
    deletions_store: InMemoryStore,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
) -> None:
    """C-22(b-2): 再書き込みモードでは要約を引き継がず `pending` に戻し、再生成を依頼する。"""
    document = make_document()
    register_one(summary_registrar, document)
    stored = stored_document(search_index, document)
    search_index.seed(
        id_of(document),
        {**stored, "summary": "old", "summary_status": "generated", "summary_model": "m"},
    )
    summary_requests.take()
    seed_result(deletions_store, make_result(rewrite_mode=True))

    register_one(summary_registrar, document)

    refreshed = stored_document(search_index, document)
    assert refreshed["summary_status"] == "pending"
    assert "summary" not in refreshed
    assert summary_requests.take() == id_of(document)


def test_full_queue_does_not_fail_the_registration(
    make_registrar,
    registration_config: RegistrationConfig,
    search_index: InMemorySearchIndex,
) -> None:
    """キューが満杯でも登録は成功し、`pending` のまま残る(再走査の対象)。"""
    full_queue = SummaryRequestQueue(max_size=1)
    registrar = make_registrar(
        replace(registration_config, summary_enabled=True), requests=full_queue
    )

    outcomes = registrar.register(make_context(), [make_document("a.txt"), make_document("b.txt")])

    assert [type(outcome) for outcome in outcomes] == [DocumentRegistered, DocumentRegistered]
    assert stored_document(search_index, "b.txt")["summary_status"] == "pending"
    assert len(full_queue) == 1
    assert full_queue.take_overflow_flag() is True


def test_existing_document_without_a_summary_status_is_reset_when_only_the_metadata_changes(
    summary_registrar: DocumentRegistrar,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
) -> None:
    """引き継ぐ状態がない文書(要約の項目なし)は、引き継がずに `pending` で生成を依頼する。"""
    document = make_document()
    register_one(summary_registrar, document)
    summary_requests.take()
    legacy = {
        name: value
        for name, value in stored_document(search_index, document).items()
        if name not in ("summary", "summary_status", "summary_model")
    }
    search_index.seed(id_of(document), legacy)

    outcome = register_one(summary_registrar, replace(document, title="B"))

    assert outcome.change is Change.UPDATED
    refreshed = stored_document(search_index, document)
    assert refreshed["title"] == "B"
    assert refreshed["summary_status"] == "pending"
    assert summary_requests.take() == id_of(document)


def break_with_a_rejection(search_index: InMemorySearchIndex, jobs_store: InMemoryStore) -> None:
    search_index.behavior.inject(ops.CREATE, Rejected("mapper_parsing_exception"))


def break_with_endless_conflicts(
    search_index: InMemorySearchIndex, jobs_store: InMemoryStore
) -> None:
    search_index.behavior.inject(ops.CREATE, Conflict(), times=None)
    search_index.behavior.inject(ops.FETCH, None, times=None)  # 読み直しても文書は見つからない


def break_with_a_lost_lock(search_index: InMemorySearchIndex, jobs_store: InMemoryStore) -> None:
    jobs_store.delete(f"lock-{SOURCE_ID}")


@pytest.mark.parametrize(
    ("break_the_write", "failure_type"),
    [
        (break_with_a_rejection, FailureType.DOCUMENT_REJECTED),
        (break_with_endless_conflicts, FailureType.WRITE_CONFLICT),
        (break_with_a_lost_lock, FailureType.LOCK_NOT_OWNED),
    ],
    ids=["document_rejected", "write_conflict", "lock_not_owned"],
)
def test_a_failed_registration_requests_no_summary(
    summary_registrar: DocumentRegistrar,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
    summary_requests: SummaryRequestQueue,
    break_the_write,
    failure_type: FailureType,
) -> None:
    """書き込みが成功したときだけ依頼する。書かれていない文書の生成を依頼しない。"""
    break_the_write(search_index, jobs_store)

    outcome = register_one(summary_registrar, make_document())

    assert isinstance(outcome, DocumentFailed)
    assert outcome.failure_type is failure_type
    assert len(summary_requests) == 0
