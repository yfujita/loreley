import pytest
from opensearchpy.exceptions import (
    AuthorizationException,
    ConflictError,
    ConnectionError,
    ConnectionTimeout,
    NotFoundError,
    RequestError,
    SSLError,
    TransportError,
)

from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    NotFound,
    OpenSearchUnavailableError,
    Rejected,
)
from loreley_indexer.infrastructure.opensearch.classification import classify_failure


def error_body(error_type: str, reason: str = "r") -> dict:
    return {"error": {"type": error_type, "reason": reason}, "status": 0}


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ConnectionError("N/A", "refused", Exception("x")), "connection_error"),
        (ConnectionTimeout("TIMEOUT", "timed out", Exception("x")), "connection_timeout"),
        (TransportError(429, "es_rejected_execution_exception", {}), "http_429"),
        (TransportError(500, "x", {}), "http_500"),
        (TransportError(502, "x", {}), "http_502"),
        (TransportError(503, "x", {}), "http_503"),
        (SSLError("N/A", "certificate verify failed", Exception("x")), "connection_error"),
        (TransportError("N/A", "unknown failure", Exception("x")), "transport_error"),
        # 認証・認可の誤りは文書固有ではなく、設定・権限の全体異常。
        (
            AuthorizationException(403, "security_exception", error_body("security_exception")),
            "http_403",
        ),
        (
            TransportError(401, "security_exception", error_body("security_exception")),
            "http_401",
        ),
        (AuthorizationException(403, "x", {}), "http_403"),
        (TransportError(401, "x", {}), "http_401"),
        (
            AuthorizationException(
                403, "cluster_block_exception", error_body("cluster_block_exception")
            ),
            "cluster_block_exception",
        ),
        (
            TransportError(429, "x", error_body("circuit_breaking_exception")),
            "circuit_breaking_exception",
        ),
        (
            NotFoundError(404, "x", error_body("index_not_found_exception")),
            "index_not_found_exception",
        ),
    ],
)
def test_cluster_wide_failures_raise_unavailable(error: TransportError, reason: str) -> None:
    with pytest.raises(OpenSearchUnavailableError) as excinfo:
        classify_failure(error)
    assert excinfo.value.reason == reason


def test_version_conflict_is_conflict() -> None:
    error = ConflictError(409, "x", error_body("version_conflict_engine_exception"))
    assert classify_failure(error) == Conflict()


@pytest.mark.parametrize(
    "info",
    [
        error_body("document_missing_exception"),
        {"_index": "i", "_id": "1", "found": False},  # GET
        {"_index": "i", "_id": "1", "result": "not_found"},  # DELETE
    ],
)
def test_missing_document_is_not_found(info: dict) -> None:
    assert classify_failure(NotFoundError(404, "x", info)) == NotFound()


def test_index_not_found_is_not_confused_with_missing_document() -> None:
    error = NotFoundError(404, "x", error_body("index_not_found_exception"))
    with pytest.raises(OpenSearchUnavailableError):
        classify_failure(error)


def test_other_4xx_is_a_document_specific_rejection_carrying_only_the_error_type() -> None:
    error = RequestError(
        400,
        "mapper_parsing_exception",
        error_body("mapper_parsing_exception", reason="failed to parse field value SENTINEL-BODY"),
    )
    outcome = classify_failure(error)
    assert outcome == Rejected(error_type="mapper_parsing_exception")
    assert "SENTINEL-BODY" not in repr(outcome)


def test_error_type_falls_back_to_the_exception_error_field_when_the_body_has_none() -> None:
    # 本文(info)が空でも、`error` 属性が `*_exception` ならそれを error_type として使う。
    error = RequestError(400, "mapper_parsing_exception", {})
    assert classify_failure(error) == Rejected(error_type="mapper_parsing_exception")


def test_4xx_without_an_error_type_is_rejected_by_status() -> None:
    assert classify_failure(TransportError(400, "bad", {})) == Rejected(error_type="http_400")


def test_404_that_is_neither_document_nor_index_is_a_rejection() -> None:
    assert classify_failure(NotFoundError(404, "x", {})) == Rejected(error_type="http_404")


def test_unavailable_error_hides_the_original_exception_chain() -> None:
    error = TransportError(503, "x", error_body("x", reason="SENTINEL-BODY"))
    with pytest.raises(OpenSearchUnavailableError) as excinfo:
        classify_failure(error)
    assert excinfo.value.__suppress_context__
    assert "SENTINEL-BODY" not in str(excinfo.value)
