"""例外の分類(C 5.8・3.2。C 11章 6)。タイムアウトを優先し、理由文・ID をログに出さない。"""

import logging

import pytest
from opensearchpy.exceptions import (
    AuthenticationException,
    AuthorizationException,
    ConnectionTimeout,
    NotFoundError,
    RequestError,
    SerializationError,
    SSLError,
    TransportError,
)
from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError
from urllib3.exceptions import (
    ConnectTimeoutError,
    NameResolutionError,
    NewConnectionError,
    ProtocolError,
    ReadTimeoutError,
)

from loreley_api.common.results import Failed, Ok
from loreley_api.infrastructure.opensearch.failure import (
    DocumentError,
    PartialResponseError,
    ResponseShapeError,
    ResultLimitExceededError,
    SubRequestError,
    failed_from_exception,
    guarded_read,
    is_timeout,
)

SECRET = "secret-index-name-and-id-42"


def connection_error(info: BaseException) -> OpenSearchConnectionError:
    return OpenSearchConnectionError("N/A", str(info), info)


# 接続のタイムアウトは `ConnectionError`(`info` が `ConnectTimeoutError`)で届く。
# `NewConnectionError`・`NameResolutionError` は `ConnectTimeoutError` の子だが、
# タイムアウトではない(UNAVAILABLE_CASES)。
TIMEOUT_CASES = [
    pytest.param(
        ConnectionTimeout("TIMEOUT", "read timed out", ReadTimeoutError(None, "u", "")),
        id="read timeout",
    ),
    pytest.param(
        connection_error(ConnectTimeoutError(None, "connect timed out")), id="connect timeout"
    ),
    pytest.param(PartialResponseError(timed_out=True), id="timed_out=true"),
]
UNAVAILABLE_CASES = [
    pytest.param(connection_error(NewConnectionError(None, "refused")), id="connection refused"),
    pytest.param(
        connection_error(NameResolutionError("h", None, OSError("x"))), id="name not resolved"
    ),
    pytest.param(connection_error(ProtocolError("reset")), id="protocol error"),
    pytest.param(SSLError("N/A", "bad cert", ProtocolError("x")), id="ssl error"),
    pytest.param(
        OpenSearchConnectionError("N/A", "x", RuntimeError("x")), id="other connection error"
    ),
    pytest.param(TransportError(503, "unavailable", {}), id="503"),
    pytest.param(TransportError(500, "boom", {}), id="500"),
    pytest.param(AuthenticationException(401, "x", {}), id="401"),
    pytest.param(AuthorizationException(403, "x", {}), id="403"),
    pytest.param(NotFoundError(404, "index_not_found_exception", {}), id="404"),
    pytest.param(RequestError(400, "parsing_exception", {}), id="400"),
    pytest.param(SerializationError("x"), id="serialization"),
    pytest.param(RuntimeError("unexpected"), id="unexpected"),
    pytest.param(PartialResponseError(timed_out=False), id="shards failed"),
    pytest.param(ResponseShapeError("x"), id="shape"),
    pytest.param(ResultLimitExceededError("x"), id="limit"),
    pytest.param(DocumentError("x"), id="document error"),
    pytest.param(SubRequestError("x"), id="sub request error"),
]


@pytest.mark.parametrize("error", TIMEOUT_CASES)
def test_timeouts_are_classified_as_timeout(error: Exception) -> None:
    assert is_timeout(error)
    failed = failed_from_exception(error, "store", operation="test.operation")
    assert failed == Failed(kind="timeout", target="store", error_class_name=type(error).__name__)


@pytest.mark.parametrize("error", UNAVAILABLE_CASES)
def test_other_failures_are_classified_as_unavailable(error: Exception) -> None:
    assert not is_timeout(error)
    failed = failed_from_exception(error, "search_index", operation="test.operation")
    assert failed == Failed(
        kind="unavailable", target="search_index", error_class_name=type(error).__name__
    )


def test_a_connect_timeout_wins_over_the_target() -> None:
    error = connection_error(ConnectTimeoutError(None, "x"))

    assert failed_from_exception(error, "search_index", operation="o").kind == "timeout"


def test_guarded_read_returns_ok_with_the_value() -> None:
    assert guarded_read("o", "store", lambda: 42) == Ok(42)


def test_guarded_read_turns_any_exception_into_failed() -> None:
    def read() -> int:
        raise KeyError(SECRET)

    assert guarded_read("o", "store", read) == Failed("unavailable", "store", "KeyError")


def test_guarded_read_does_not_swallow_base_exceptions() -> None:
    def read() -> int:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        guarded_read("o", "store", read)


def test_a_failure_log_has_only_fixed_items_and_not_the_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = TransportError(503, SECRET, {"error": {"root_cause": [{"reason": SECRET}]}})

    with caplog.at_level(logging.DEBUG):
        failed_from_exception(error, "store", operation="jobs.list_jobs")

    [record] = caplog.records
    assert record.levelno == logging.WARNING
    message = record.getMessage()
    assert "operation=jobs.list_jobs" in message
    assert "error=TransportError" in message
    assert "status=503" in message
    assert SECRET not in message
    assert record.exc_info is None


def test_a_rejected_request_is_logged_as_an_error_with_the_error_type_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    info = {"error": {"type": "parsing_exception", "reason": SECRET, "root_cause": [SECRET]}}

    with caplog.at_level(logging.DEBUG):
        failed_from_exception(RequestError(400, "x", info), "store", operation="jobs.list_jobs")

    [record] = caplog.records
    assert record.levelno == logging.ERROR
    assert "error_type=parsing_exception" in record.getMessage()
    assert SECRET not in record.getMessage()


@pytest.mark.parametrize(
    "info",
    [
        {},
        {"error": "string"},
        {"error": {"type": SECRET}},
        {"error": {"type": ["x"]}},
        "not a mapping",
        None,
    ],
)
def test_an_unsafe_or_missing_error_type_is_not_logged(
    info: object, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        failed_from_exception(RequestError(400, "x", info), "store", operation="o")

    assert "error_type=unknown" in caplog.records[0].getMessage()
    assert SECRET not in caplog.records[0].getMessage()


def test_a_non_integer_status_is_logged_as_not_applicable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        failed_from_exception(
            connection_error(NewConnectionError(None, SECRET)), "store", operation="o"
        )

    message = caplog.records[0].getMessage()
    assert "status=n/a" in message
    assert SECRET not in message
