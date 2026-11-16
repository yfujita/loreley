"""`connectors/interface/` の型・エラー分類(interface 3.2・6章)。"""

import copy
import dataclasses
import errno
import logging
import pickle
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone

import pytest

from loreley_crawler.connectors.interface import (
    Completed,
    ConnectorError,
    DocumentMetadata,
    DocumentRef,
    ErrorCategory,
    ErrorScope,
    FetchedDocument,
    RetryHint,
    converting_unexpected_errors,
    errno_name,
    to_connector_error,
)
from tests.error_text import logged_text

# interface 6.2 の表(連結の `connector_internal_error` を除く)。
SCOPE_AND_RETRY = {
    "config_invalid": ("source", "permanent"),
    "source_unreachable": ("source", "transient"),
    "source_not_found": ("source", "permanent"),
    "source_access_denied": ("source", "permanent"),
    "enumeration_incomplete": ("source", "unknown"),
    "fetch_not_found": ("document", "permanent"),
    "fetch_permission_denied": ("document", "permanent"),
    "fetch_transient": ("document", "transient"),
    "oversize": ("document", "permanent"),
    "invalid_external_id": ("document", "permanent"),
    "external_id_collision": ("document", "permanent"),
}


def test_the_categories_are_exactly_those_of_the_design() -> None:
    assert {category.value for category in ErrorCategory} == {
        *SCOPE_AND_RETRY,
        "connector_internal_error",
    }


@pytest.mark.parametrize(("name", "expected"), SCOPE_AND_RETRY.items())
def test_scope_and_retry_follow_the_table_of_the_design(
    name: str, expected: tuple[str, str]
) -> None:
    error = ConnectorError.of(ErrorCategory(name), "message")

    assert (error.category.value, error.scope.value, error.retry.value) == (name, *expected)
    assert error.message == "message"


@pytest.mark.parametrize("scope", [ErrorScope.SOURCE, ErrorScope.DOCUMENT])
def test_the_scope_of_an_internal_error_is_given_by_the_call_site(scope: ErrorScope) -> None:
    error = ConnectorError.of(ErrorCategory.CONNECTOR_INTERNAL_ERROR, "m", scope=scope)

    assert (error.scope, error.retry) == (scope, RetryHint.UNKNOWN)


def test_an_internal_error_needs_a_scope_and_other_categories_reject_one() -> None:
    with pytest.raises(ValueError, match="scope"):
        ConnectorError.of(ErrorCategory.CONNECTOR_INTERNAL_ERROR, "m")
    with pytest.raises(ValueError, match="scope"):
        ConnectorError.of(ErrorCategory.OVERSIZE, "m", scope=ErrorScope.SOURCE)


def test_str_of_the_error_is_its_message() -> None:
    assert str(ConnectorError.of(ErrorCategory.OVERSIZE, "too big")) == "too big"


@pytest.mark.parametrize(
    "duplicate", [copy.copy, copy.deepcopy, lambda e: pickle.loads(pickle.dumps(e))]
)
def test_the_error_survives_copying_and_pickling(
    duplicate: Callable[[ConnectorError], object],
) -> None:
    error = ConnectorError.of(
        ErrorCategory.CONNECTOR_INTERNAL_ERROR, "m", scope=ErrorScope.DOCUMENT
    )

    restored = duplicate(error)

    assert isinstance(restored, ConnectorError)
    assert (restored.category, restored.scope, restored.retry, restored.message) == (
        ErrorCategory.CONNECTOR_INTERNAL_ERROR,
        ErrorScope.DOCUMENT,
        RetryHint.UNKNOWN,
        "m",
    )


def test_errno_names() -> None:
    assert errno_name(OSError(errno.EACCES, "denied")) == "EACCES"
    assert errno_name(OSError("no errno")) == "UNKNOWN"
    assert errno_name(OSError(99999, "unknown code")) == "UNKNOWN"


def test_an_unexpected_exception_becomes_an_internal_error_without_its_message() -> None:
    error = to_connector_error(ValueError("SECRET-PASSWORD in /private/path"), ErrorScope.SOURCE)

    assert error.category is ErrorCategory.CONNECTOR_INTERNAL_ERROR
    assert error.scope is ErrorScope.SOURCE
    assert error.retry is RetryHint.UNKNOWN
    assert "ValueError" in error.message
    assert "SECRET" not in error.message
    assert "/private/path" not in error.message


def test_an_os_error_is_converted_with_its_errno_name_but_not_its_path() -> None:
    error = to_connector_error(
        OSError(errno.EMFILE, "Too many open files", "/secret"), ErrorScope.DOCUMENT
    )

    assert error.scope is ErrorScope.DOCUMENT
    assert "OSError" in error.message
    assert "EMFILE" in error.message
    assert "/secret" not in error.message


def test_converting_passes_a_connector_error_through_unchanged() -> None:
    original = ConnectorError.of(ErrorCategory.FETCH_TRANSIENT, "m")

    with pytest.raises(ConnectorError) as exc_info, converting_unexpected_errors(ErrorScope.SOURCE):
        raise original

    assert exc_info.value is original


def test_converting_changes_other_exceptions_and_does_not_chain_the_original() -> None:
    with (
        pytest.raises(ConnectorError) as exc_info,
        converting_unexpected_errors(ErrorScope.DOCUMENT),
    ):
        raise RuntimeError("SENTINEL-DETAIL")

    error = exc_info.value
    assert error.category is ErrorCategory.CONNECTOR_INTERNAL_ERROR
    assert error.scope is ErrorScope.DOCUMENT
    # 元の例外のメッセージ(ファイル名・値の repr)が、ログに出る連鎖に残らない(R11)。
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
    assert "SENTINEL" not in logged_text(error)


@pytest.mark.parametrize(
    "original",
    [
        OSError(errno.EIO, "io SENTINEL-MESSAGE", "/SENTINEL-FILENAME\nforged line"),
        TypeError("SENTINEL-VALUE"),
        KeyError("SENTINEL-KEY"),
    ],
)
def test_the_logged_traceback_of_a_converted_error_never_shows_the_original_text(
    original: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    logger = logging.getLogger("test-converting")

    try:
        with converting_unexpected_errors(ErrorScope.SOURCE):
            raise original
    except ConnectorError:
        logger.exception("enumeration failed")

    assert "enumeration failed" in caplog.text
    assert "ConnectorError" in caplog.text
    assert "SENTINEL" not in caplog.text
    assert "forged line" not in caplog.text


def test_converting_does_not_swallow_interruptions() -> None:
    with pytest.raises(KeyboardInterrupt), converting_unexpected_errors(ErrorScope.SOURCE):
        raise KeyboardInterrupt


def test_converting_passes_a_normal_block_through() -> None:
    with converting_unexpected_errors(ErrorScope.SOURCE):
        value = 1

    assert value == 1


def test_stop_iteration_is_converted_not_treated_as_completion() -> None:
    with pytest.raises(ConnectorError), converting_unexpected_errors(ErrorScope.SOURCE):
        raise StopIteration


# --- 型 ---


def test_value_types_are_frozen() -> None:
    ref = DocumentRef("a", "a")
    metadata = DocumentMetadata("t", "text/plain", datetime(2026, 1, 1, tzinfo=UTC))
    fetched = FetchedDocument(b"x", metadata)

    for instance, attribute in [(ref, "external_id"), (metadata, "title"), (fetched, "content")]:
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, attribute, "changed")


def test_a_document_ref_defaults_to_no_size_hint_and_keeps_an_opaque_locator() -> None:
    locator = ("opaque", 1)

    ref = DocumentRef("id", locator)

    assert ref.size_hint is None
    assert ref.locator is locator


def test_optional_metadata_defaults_to_none() -> None:
    metadata = DocumentMetadata("t", "text/plain", datetime(2026, 1, 1, tzinfo=UTC))

    assert (metadata.path, metadata.url) == (None, None)


def test_metadata_requires_a_timezone_aware_modification_time() -> None:
    with pytest.raises(ValueError, match="timezone"):
        DocumentMetadata("t", "text/plain", datetime(2026, 1, 1))
    DocumentMetadata("t", "text/plain", datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=9))))


def test_completed_is_a_distinct_value_that_is_not_a_document_ref() -> None:
    assert Completed() == Completed()
    assert not isinstance(Completed(), DocumentRef)
