"""取得の包み(interface 4章・5.4・7章・10章 #5・#9。architecture 12章 #19・#22)。"""

import hashlib
from datetime import UTC, datetime

import pytest

from loreley_crawler.connectors.interface import (
    ConnectorError,
    DocumentMetadata,
    DocumentRef,
    ErrorCategory,
    ErrorScope,
    FetchedDocument,
    RetryHint,
)
from loreley_crawler.documents import DocumentFetcher, DocumentsSettings
from tests.fakes.fake_connector import FETCH, FakeConnector, fetched_document

MODIFIED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
LONE_SURROGATE = chr(0xD800)


def fetcher_for(connector: FakeConnector, max_raw_bytes: int = 1024) -> DocumentFetcher:
    return DocumentFetcher(connector, settings=DocumentsSettings(max_raw_bytes=max_raw_bytes))


def ref(name: str, size_hint: int | None = None) -> DocumentRef:
    return DocumentRef(external_id=name, locator=name, size_hint=size_hint)


# --- #5 content_hash と size ---


def test_content_hash_and_size_are_computed_from_the_bytes_that_will_be_sent() -> None:
    content = "日本語の本文".encode() + bytes(range(256))
    connector = FakeConnector.of({"a.txt": content})

    prepared = fetcher_for(connector).fetch(ref("a.txt"))

    assert prepared.content == content
    assert prepared.content_hash == hashlib.sha256(content).hexdigest()
    assert len(prepared.content_hash) == 64
    assert prepared.content_hash == prepared.content_hash.lower()
    assert prepared.size == len(content)


def test_an_empty_original_has_size_zero_and_the_known_hash() -> None:
    connector = FakeConnector.of({"empty.txt": b""})

    prepared = fetcher_for(connector).fetch(ref("empty.txt"))

    assert prepared.size == 0
    assert prepared.content_hash == EMPTY_SHA256


def test_the_hash_follows_the_content_even_if_the_original_changes_between_fetches() -> None:
    connector = FakeConnector.of({"a.txt": b"first"})
    fetcher = fetcher_for(connector)
    first = fetcher.fetch(ref("a.txt"))
    connector.documents["a.txt"] = fetched_document(b"second version")

    second = fetcher.fetch(ref("a.txt"))

    assert first.content_hash == hashlib.sha256(b"first").hexdigest()
    assert second.content_hash == hashlib.sha256(b"second version").hexdigest()
    assert second.size == len(b"second version")


# --- #9 取得 ---


def test_the_same_ref_can_be_fetched_twice() -> None:
    connector = FakeConnector.of({"a.txt": b"content"})
    fetcher = fetcher_for(connector)

    assert fetcher.fetch(ref("a.txt")) == fetcher.fetch(ref("a.txt"))


def test_the_limit_is_passed_to_the_connector_as_max_bytes() -> None:
    connector = FakeConnector.of({"a.txt": b"x"})

    fetcher_for(connector, max_raw_bytes=777).fetch(ref("a.txt"))

    assert [max_bytes for _, max_bytes in connector.fetch_calls] == [777]


def test_an_original_of_exactly_the_limit_is_accepted() -> None:
    connector = FakeConnector.of({"a.txt": b"x" * 10})

    assert fetcher_for(connector, max_raw_bytes=10).fetch(ref("a.txt")).size == 10


def test_an_oversize_error_of_the_connector_passes_through() -> None:
    connector = FakeConnector.of({"a.txt": b"x" * 11})

    with pytest.raises(ConnectorError) as exc_info:
        fetcher_for(connector, max_raw_bytes=10).fetch(ref("a.txt"))

    error = exc_info.value
    assert (error.category, error.scope, error.retry) == (
        ErrorCategory.OVERSIZE,
        ErrorScope.DOCUMENT,
        RetryHint.PERMANENT,
    )


def test_a_size_hint_over_the_limit_is_oversize_without_calling_the_connector() -> None:
    connector = FakeConnector.of({"a.txt": b"small"})

    with pytest.raises(ConnectorError) as exc_info:
        fetcher_for(connector, max_raw_bytes=10).fetch(ref("a.txt", size_hint=11))

    assert exc_info.value.category is ErrorCategory.OVERSIZE
    assert connector.fetch_calls == []  # 読まない


def test_a_size_hint_within_the_limit_does_not_block_the_fetch() -> None:
    connector = FakeConnector.of({"a.txt": b"small"})

    assert fetcher_for(connector, max_raw_bytes=10).fetch(ref("a.txt", size_hint=10)).size == 5
    assert fetcher_for(connector, max_raw_bytes=10).fetch(ref("a.txt", size_hint=0)).size == 5


def test_a_connector_that_returns_more_than_the_limit_is_still_oversize() -> None:
    connector = FakeConnector.of({"a.txt": b"x"})
    connector.behavior.inject(FETCH, fetched_document(b"y" * 11))

    with pytest.raises(ConnectorError) as exc_info:
        fetcher_for(connector, max_raw_bytes=10).fetch(ref("a.txt"))

    assert exc_info.value.category is ErrorCategory.OVERSIZE


# --- メタデータ ---


def test_lone_surrogates_in_the_metadata_are_replaced_for_display() -> None:
    metadata = DocumentMetadata(
        title=f"t{LONE_SURROGATE}.txt",
        mime_type=f"text/{LONE_SURROGATE}",
        source_updated_at=MODIFIED_AT,
        path=f"dir/{LONE_SURROGATE}/a.txt",
        url=f"https://example.invalid/{LONE_SURROGATE}",
    )
    connector = FakeConnector()
    connector.behavior.inject(FETCH, FetchedDocument(b"x", metadata))

    prepared = fetcher_for(connector).fetch(ref("a.txt")).metadata

    replacement = chr(0xFFFD)
    assert prepared.title == f"t{replacement}.txt"
    assert prepared.mime_type == f"text/{replacement}"
    assert prepared.path == f"dir/{replacement}/a.txt"
    assert prepared.url == f"https://example.invalid/{replacement}"
    for value in (prepared.title, prepared.mime_type, prepared.path, prepared.url):
        value.encode("utf-8")  # Indexer が `document_rejected` にしない(例外にならない)
    assert prepared.source_updated_at == MODIFIED_AT


def test_absent_path_and_url_stay_absent_and_other_values_are_unchanged() -> None:
    metadata = DocumentMetadata("タイトル", "text/markdown", MODIFIED_AT)
    connector = FakeConnector()
    connector.behavior.inject(FETCH, FetchedDocument(b"x", metadata))

    assert fetcher_for(connector).fetch(ref("a.md")).metadata == metadata


# --- 失敗 ---


def test_a_connector_error_passes_through_unchanged() -> None:
    connector = FakeConnector.of({"a.txt": b"x"})
    failure = ConnectorError.of(ErrorCategory.FETCH_TRANSIENT, "changed while reading")
    connector.behavior.inject(FETCH, failure, key="a.txt")

    with pytest.raises(ConnectorError) as exc_info:
        fetcher_for(connector).fetch(ref("a.txt"))

    # fake は注入した例外を複製して送出するので、同一性ではなく中身を比べる。
    assert (exc_info.value.category, exc_info.value.message) == (failure.category, failure.message)
    assert (exc_info.value.scope, exc_info.value.retry) == (failure.scope, failure.retry)


def test_a_missing_document_is_fetch_not_found() -> None:
    connector = FakeConnector.of({})

    with pytest.raises(ConnectorError) as exc_info:
        fetcher_for(connector).fetch(ref("gone.txt"))

    assert exc_info.value.category is ErrorCategory.FETCH_NOT_FOUND


@pytest.mark.parametrize("error", [RuntimeError("SECRET-DETAIL"), OSError(24, "too many")])
def test_an_unexpected_exception_becomes_an_internal_error_of_scope_document(
    error: Exception,
) -> None:
    connector = FakeConnector.of({"a.txt": b"x"})
    connector.behavior.inject(FETCH, error)

    with pytest.raises(ConnectorError) as exc_info:
        fetcher_for(connector).fetch(ref("a.txt"))

    converted = exc_info.value
    assert converted.category is ErrorCategory.CONNECTOR_INTERNAL_ERROR
    assert (converted.scope, converted.retry) == (ErrorScope.DOCUMENT, RetryHint.UNKNOWN)
    assert "SECRET" not in converted.message
    assert converted.__cause__ is None  # 元の例外を連鎖に残さない(R11)


class _NotADocument:
    pass


@pytest.mark.parametrize(
    "bad_result",
    [
        FetchedDocument("text instead of bytes", DocumentMetadata("t", "text/plain", MODIFIED_AT)),  # type: ignore[arg-type]
        FetchedDocument(b"x", DocumentMetadata(None, "text/plain", MODIFIED_AT)),  # type: ignore[arg-type]
        FetchedDocument(b"x", DocumentMetadata("t", None, MODIFIED_AT)),  # type: ignore[arg-type]
        FetchedDocument(b"x", None),  # type: ignore[arg-type]
        _NotADocument(),
        None,
    ],
    ids=["str-content", "none-title", "none-mime", "none-metadata", "wrong-type", "none"],
)
def test_an_invalid_return_value_is_an_internal_error_of_scope_document(
    bad_result: object,
) -> None:
    connector = FakeConnector.of({"a.txt": b"x"})
    connector.behavior.inject(FETCH, bad_result)

    with pytest.raises(ConnectorError) as exc_info:
        fetcher_for(connector).fetch(ref("a.txt"))

    error = exc_info.value
    assert error.category is ErrorCategory.CONNECTOR_INTERNAL_ERROR
    assert (error.scope, error.retry) == (ErrorScope.DOCUMENT, RetryHint.UNKNOWN)
