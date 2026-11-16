"""列挙の包み(interface 5.3・10章 #4・#7。architecture 12章 #7・#21・#22)。"""

import pytest

from loreley_crawler.connectors.interface import (
    Completed,
    ConnectorError,
    DocumentRef,
    ErrorCategory,
    ErrorScope,
    RetryHint,
)
from loreley_crawler.documents import (
    DocumentEnumeration,
    DocumentsSettings,
    EnumeratedDocument,
    EnumerationResult,
    EnumerationTooLargeError,
    InvalidExternalId,
    compute_document_id,
)
from tests.fakes.fake_connector import NEXT, FakeConnector

SOURCE_ID = "src-fs"
LONE_SURROGATE = chr(0xDC80)


def enumeration_of(
    *items: DocumentRef | Completed | BaseException,
    settings: DocumentsSettings | None = None,
) -> tuple[DocumentEnumeration, FakeConnector]:
    connector = FakeConnector(items)
    enumeration = DocumentEnumeration(
        connector.enumerate(), source_id=SOURCE_ID, settings=settings or DocumentsSettings()
    )
    return enumeration, connector


def ref(external_id: str) -> DocumentRef:
    return DocumentRef(external_id=external_id, locator=f"locator:{external_id}")


def drain(enumeration: DocumentEnumeration) -> list[EnumerationResult]:
    results: list[EnumerationResult] = []
    while True:
        result = enumeration.next()
        results.append(result)
        if isinstance(result, Completed):
            return results


def test_documents_are_returned_with_the_final_external_id_the_id_and_the_original_ref() -> None:
    first = ref("docs/a.md")
    enumeration, _ = enumeration_of(first, ref("b.txt"), Completed())

    results = drain(enumeration)

    assert results == [
        EnumeratedDocument(compute_document_id(SOURCE_ID, "docs/a.md"), "docs/a.md", first),
        EnumeratedDocument(compute_document_id(SOURCE_ID, "b.txt"), "b.txt", ref("b.txt")),
        Completed(),
    ]
    assert enumeration.enumerated_count == 2


def test_the_final_form_is_what_the_document_id_is_computed_from() -> None:
    enumeration, _ = enumeration_of(ref("a\\b.txt"), Completed())

    [document, _] = drain(enumeration)

    assert isinstance(document, EnumeratedDocument)
    assert document.external_id == "a/b.txt"
    assert document.ref.external_id == "a\\b.txt"  # 元の参照は変えない(`fetch` に渡す)
    assert document.document_id == compute_document_id(SOURCE_ID, "a/b.txt")


def test_an_empty_enumeration_completes_with_zero_documents() -> None:
    enumeration, _ = enumeration_of(Completed())

    assert drain(enumeration) == [Completed()]
    assert enumeration.enumerated_count == 0


# --- #7 重複 ---


def test_the_same_document_returned_twice_is_counted_once_and_returned_once() -> None:
    enumeration, _ = enumeration_of(ref("a.txt"), ref("b.txt"), ref("a.txt"), Completed())

    results = drain(enumeration)

    assert [r.external_id for r in results if isinstance(r, EnumeratedDocument)] == [
        "a.txt",
        "b.txt",
    ]
    assert enumeration.enumerated_count == 2


def test_a_duplicate_with_a_different_locator_is_still_a_duplicate() -> None:
    first = DocumentRef("a.txt", locator="one")
    again = DocumentRef("a.txt", locator="two")
    enumeration, _ = enumeration_of(first, again, Completed())

    results = drain(enumeration)

    assert [r.ref for r in results if isinstance(r, EnumeratedDocument)] == [first]


def test_duplicates_are_detected_for_ids_with_lone_surrogates_too() -> None:
    name = f"x{LONE_SURROGATE}.txt"
    enumeration, _ = enumeration_of(ref(name), ref(name), Completed())

    results = drain(enumeration)

    assert len([r for r in results if isinstance(r, EnumeratedDocument)]) == 1
    assert enumeration.enumerated_count == 1


# --- #4 衝突の検出 ---


def test_a_backslash_name_and_a_slash_name_with_the_same_id_are_a_collision() -> None:
    enumeration, _ = enumeration_of(ref("a\\b.txt"), ref("a/b.txt"), Completed())

    assert isinstance(enumeration.next(), EnumeratedDocument)
    with pytest.raises(ConnectorError) as exc_info:
        enumeration.next()

    error = exc_info.value
    assert error.category is ErrorCategory.EXTERNAL_ID_COLLISION
    assert error.scope is ErrorScope.DOCUMENT
    assert error.retry is RetryHint.PERMANENT
    # `failure_detail` には、後に検出された 1 件の external_id と共有する document_id を載せる。
    assert "a/b.txt" in error.message
    assert compute_document_id(SOURCE_ID, "a/b.txt") in error.message


def test_nfc_and_nfd_names_with_the_same_id_are_a_collision() -> None:
    nfc = chr(0x304C) + ".txt"
    nfd = chr(0x304B) + chr(0x3099) + ".txt"
    enumeration, _ = enumeration_of(ref(nfc), ref(nfd), Completed())

    enumeration.next()
    with pytest.raises(ConnectorError) as exc_info:
        enumeration.next()

    assert exc_info.value.category is ErrorCategory.EXTERNAL_ID_COLLISION


def test_the_collision_message_shows_the_external_id_in_a_safe_truncated_form() -> None:
    long_name = "dir/" + "x" * 300
    enumeration, _ = enumeration_of(
        ref(f"{long_name}\nline\\.txt"), ref(f"{long_name}\nline/.txt"), Completed()
    )
    enumeration.next()

    with pytest.raises(ConnectorError) as exc_info:
        enumeration.next()

    message = exc_info.value.message
    assert "\n" not in message
    assert "x" * 201 not in message


def test_a_collision_ends_the_enumeration_and_the_failure_repeats() -> None:
    enumeration, connector = enumeration_of(ref("a\\b"), ref("a/b"), ref("c"), Completed())
    enumeration.next()
    with pytest.raises(ConnectorError) as first:
        enumeration.next()

    with pytest.raises(ConnectorError) as second:
        enumeration.next()

    assert second.value is first.value  # 失敗の後に続きを返さない
    assert enumeration.enumerated_count == 1
    assert len(connector.streams) == 1


# --- 識別子エラー ---


def test_an_invalid_external_id_is_reported_and_the_enumeration_continues() -> None:
    enumeration, _ = enumeration_of(ref("/leading"), ref("ok.txt"), ref(""), Completed())

    results = drain(enumeration)

    invalid = [r for r in results if isinstance(r, InvalidExternalId)]
    assert [i.error.category for i in invalid] == [ErrorCategory.INVALID_EXTERNAL_ID] * 2
    assert [r.external_id for r in results if isinstance(r, EnumeratedDocument)] == ["ok.txt"]
    assert enumeration.enumerated_count == 1  # 識別子エラーの文書は `enumerated_count` に含めない
    assert not enumeration.has_enumerated(compute_document_id(SOURCE_ID, "/leading"))


def test_the_invalid_id_is_shown_as_a_safe_truncated_display_string() -> None:
    raw = "/" + "x" * 300 + f"\n{LONE_SURROGATE}"
    enumeration, _ = enumeration_of(ref(raw), Completed())

    [invalid, _] = drain(enumeration)

    assert isinstance(invalid, InvalidExternalId)
    assert invalid.display_external_id == "/" + "x" * 199  # 200 文字に切り詰め
    assert "x" * 300 not in invalid.error.message  # 説明文は値を含まない


def test_the_display_string_escapes_control_characters_and_replaces_lone_surrogates() -> None:
    enumeration, _ = enumeration_of(ref(f"/a\nb{LONE_SURROGATE}"), Completed())

    [invalid, _] = drain(enumeration)

    assert isinstance(invalid, InvalidExternalId)
    assert invalid.display_external_id == "/a\\nb" + chr(0xFFFD)


def test_the_display_length_is_configurable() -> None:
    enumeration, _ = enumeration_of(
        ref("/abcdefghij"), Completed(), settings=DocumentsSettings(display_max_chars=4)
    )

    [invalid, _] = drain(enumeration)

    assert isinstance(invalid, InvalidExternalId)
    assert invalid.display_external_id == "/abc"


def test_a_lone_surrogate_name_is_escaped_into_a_valid_id() -> None:
    enumeration, _ = enumeration_of(ref(f"a{LONE_SURROGATE}.txt"), Completed())

    [document, _] = drain(enumeration)

    assert isinstance(document, EnumeratedDocument)
    assert document.external_id == f"a{chr(0xFFFD)}uDC80.txt"
    document.external_id.encode("utf-8")  # Indexer に送れる(例外にならない)


# --- ID の集合の照会 ---


def test_has_enumerated_answers_for_the_ids_returned_so_far() -> None:
    enumeration, _ = enumeration_of(ref("a.txt"), ref("b.txt"), Completed())
    a_id = compute_document_id(SOURCE_ID, "a.txt")
    b_id = compute_document_id(SOURCE_ID, "b.txt")
    assert not enumeration.has_enumerated(a_id)

    enumeration.next()
    assert enumeration.has_enumerated(a_id)
    assert not enumeration.has_enumerated(b_id)

    enumeration.next()
    assert enumeration.has_enumerated(b_id)
    assert enumeration.enumerated_count == 2
    assert not enumeration.has_enumerated(compute_document_id("other-source", "a.txt"))


# --- max_enumerated_documents ---


def test_exceeding_the_limit_fails_with_a_dedicated_error() -> None:
    settings = DocumentsSettings(max_enumerated_documents=2)
    enumeration, _ = enumeration_of(ref("a"), ref("b"), ref("c"), Completed(), settings=settings)

    enumeration.next()
    enumeration.next()
    with pytest.raises(EnumerationTooLargeError) as exc_info:
        enumeration.next()

    assert exc_info.value.max_enumerated_documents == 2
    assert enumeration.enumerated_count == 2
    with pytest.raises(EnumerationTooLargeError):  # 失敗の後に続きを返さない
        enumeration.next()


def test_a_limit_of_n_allows_exactly_n_documents_and_duplicates_do_not_count() -> None:
    settings = DocumentsSettings(max_enumerated_documents=2)
    enumeration, _ = enumeration_of(
        ref("a"), ref("b"), ref("a"), ref("b"), Completed(), settings=settings
    )

    results = drain(enumeration)

    assert results[-1] == Completed()
    assert enumeration.enumerated_count == 2


def test_invalid_ids_do_not_count_toward_the_limit() -> None:
    settings = DocumentsSettings(max_enumerated_documents=1)
    enumeration, _ = enumeration_of(ref("/x"), ref("/y"), ref("ok"), Completed(), settings=settings)

    results = drain(enumeration)

    assert results[-1] == Completed()


# --- Connector の失敗・想定外の例外 ---


def test_a_connector_error_of_the_stream_passes_through_and_repeats() -> None:
    failure = ConnectorError.of(ErrorCategory.ENUMERATION_INCOMPLETE, "unreadable")
    enumeration, connector = enumeration_of(ref("a"), failure, Completed())
    enumeration.next()

    with pytest.raises(ConnectorError) as first:
        enumeration.next()
    with pytest.raises(ConnectorError) as second:
        enumeration.next()

    assert first.value is failure
    assert second.value is failure
    assert connector.streams[0].closed is False  # 打ち切るかどうかは呼び出し側の判断


@pytest.mark.parametrize("error", [RuntimeError("SECRET-DETAIL"), OSError(24, "too many")])
def test_an_unexpected_exception_becomes_an_internal_error_of_scope_source(
    error: Exception,
) -> None:
    enumeration, _ = enumeration_of(ref("a"), error, Completed())
    enumeration.next()

    with pytest.raises(ConnectorError) as exc_info:
        enumeration.next()

    converted = exc_info.value
    assert converted.category is ErrorCategory.CONNECTOR_INTERNAL_ERROR
    assert (converted.scope, converted.retry) == (ErrorScope.SOURCE, RetryHint.UNKNOWN)
    assert "SECRET" not in converted.message
    assert converted.__cause__ is None  # 元の例外を連鎖に残さない(R11)
    with pytest.raises(ConnectorError) as again:  # 再度の `next()` が完了にならない
        enumeration.next()
    assert again.value is converted


def test_stop_iteration_from_a_stream_is_a_failure_not_a_completion() -> None:
    enumeration, _ = enumeration_of(ref("a"), StopIteration(), Completed())
    enumeration.next()

    with pytest.raises(ConnectorError) as exc_info:
        enumeration.next()

    assert exc_info.value.category is ErrorCategory.CONNECTOR_INTERNAL_ERROR


@pytest.mark.parametrize("bad_item", [None, "a.txt", 1, object()])
def test_a_stream_returning_something_else_is_an_internal_error(bad_item: object) -> None:
    connector = FakeConnector()
    connector.behavior.inject(NEXT, bad_item)
    enumeration = DocumentEnumeration(
        connector.enumerate(), source_id=SOURCE_ID, settings=DocumentsSettings()
    )

    with pytest.raises(ConnectorError) as exc_info:
        enumeration.next()

    assert exc_info.value.category is ErrorCategory.CONNECTOR_INTERNAL_ERROR
    assert exc_info.value.scope is ErrorScope.SOURCE


def test_a_ref_whose_external_id_is_not_a_string_is_an_internal_error() -> None:
    enumeration, _ = enumeration_of(DocumentRef(external_id=None, locator="x"), Completed())  # type: ignore[arg-type]

    with pytest.raises(ConnectorError) as exc_info:
        enumeration.next()

    assert exc_info.value.category is ErrorCategory.CONNECTOR_INTERNAL_ERROR


def test_closing_the_enumeration_closes_only_the_stream() -> None:
    enumeration, connector = enumeration_of(ref("a"), Completed())

    enumeration.close()

    assert connector.streams[0].closed is True
    assert connector.close_count == 0  # Connector 自体は閉じない(`fetch` に使い続けられる)


def test_a_source_id_with_nul_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="NUL"):
        DocumentEnumeration(
            FakeConnector().enumerate(), source_id="a\x00b", settings=DocumentsSettings()
        )


def test_the_settings_are_validated() -> None:
    for kwargs in (
        {"max_raw_bytes": -1},
        {"max_enumerated_documents": 0},
        {"display_max_chars": 0},
    ):
        with pytest.raises(ValueError):
            DocumentsSettings(**kwargs)
    assert DocumentsSettings().max_raw_bytes == 20 * 1024 * 1024
    assert DocumentsSettings().max_enumerated_documents == 500_000
    assert DocumentsSettings(max_raw_bytes=0).max_raw_bytes == 0


# --- 終端は 1 つ(interface 3.3 の 1) ---


def test_after_completed_the_connector_is_not_called_again() -> None:
    enumeration, connector = enumeration_of(ref("a"), Completed())
    drain(enumeration)
    calls_before = len(connector.behavior.calls_of(NEXT))

    assert enumeration.next() == Completed()
    assert enumeration.next() == Completed()

    assert len(connector.behavior.calls_of(NEXT)) == calls_before


def test_close_after_completion_keeps_the_held_completed() -> None:
    # 完了した列挙は、後から `close` しても完了のまま(終端は 1 つ。Connector を呼ばない)。
    enumeration, connector = enumeration_of(ref("a"), Completed())
    drain(enumeration)

    enumeration.close()

    assert connector.streams[0].closed is True
    assert enumeration.next() == Completed()


def test_next_after_close_is_a_stored_internal_error_not_a_completion() -> None:
    enumeration, _ = enumeration_of(ref("a"), ref("b"), Completed())
    enumeration.next()
    enumeration.close()

    with pytest.raises(ConnectorError) as first:
        enumeration.next()
    with pytest.raises(ConnectorError) as second:
        enumeration.next()

    # 打ち切った列挙は完了にならない。stream の `RuntimeError` が内部エラーとして固定される。
    assert first.value.category is ErrorCategory.CONNECTOR_INTERNAL_ERROR
    assert first.value.scope is ErrorScope.SOURCE
    assert second.value is first.value


def test_the_same_invalid_document_returned_twice_is_reported_twice() -> None:
    # `document_id` を持たないので重複を除けない(個別の `invalid_id_count` が 2 になる仕様)。
    enumeration, _ = enumeration_of(ref("/bad"), ref("/bad"), Completed())

    results = drain(enumeration)

    assert [type(r) for r in results] == [InvalidExternalId, InvalidExternalId, Completed]
    assert enumeration.enumerated_count == 0


def test_a_four_byte_character_is_kept_and_not_escaped_as_a_lone_surrogate() -> None:
    name = "メモ\U0001f600.txt"
    enumeration, _ = enumeration_of(ref(name), Completed())

    [document, _] = drain(enumeration)

    assert isinstance(document, EnumeratedDocument)
    assert document.external_id == name
    assert chr(0xFFFD) not in document.external_id
    assert document.document_id == compute_document_id(SOURCE_ID, name)
