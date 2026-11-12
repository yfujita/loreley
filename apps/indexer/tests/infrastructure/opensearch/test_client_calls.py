import pytest
from opensearchpy.exceptions import ConflictError, NotFoundError, RequestError, TransportError

from loreley_indexer.infrastructure.opensearch import (
    OpenSearchUnavailableError,
    OpenSearchUnexpectedResponseError,
)
from loreley_indexer.infrastructure.opensearch.client_calls import run_query


def raising(error: TransportError):
    def call() -> dict:
        raise error

    return call


def test_run_query_returns_the_response() -> None:
    assert run_query(lambda: {"count": 3}) == {"count": 3}


@pytest.mark.parametrize(
    ("error", "expected_error_type"),
    [
        (
            RequestError(400, "x", {"error": {"type": "parsing_exception", "reason": "SENTINEL"}}),
            "parsing_exception",
        ),
        (RequestError(400, "x", {}), "http_400"),
        (ConflictError(409, "x", {}), "conflict"),
        (NotFoundError(404, "x", {"found": False}), "notfound"),
    ],
)
def test_run_query_reports_a_non_cluster_failure_as_an_unexpected_response(
    error: TransportError, expected_error_type: str
) -> None:
    with pytest.raises(OpenSearchUnexpectedResponseError) as excinfo:
        run_query(raising(error))
    assert excinfo.value.error_type == expected_error_type
    assert "SENTINEL" not in str(excinfo.value)
    assert excinfo.value.__suppress_context__


def test_run_query_keeps_cluster_wide_failures_as_unavailable() -> None:
    with pytest.raises(OpenSearchUnavailableError):
        run_query(raising(TransportError(503, "x", {})))
