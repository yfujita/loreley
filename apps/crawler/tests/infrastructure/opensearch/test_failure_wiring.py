"""Repository のどの操作も、OpenSearch 全体の異常を `StoreUnavailableError` で伝えること。

分類そのもの(`classify_failure`)は test_classification.py で確かめる。ここは、各操作がその分類を
通していること(例外を握りつぶさない、別の結果にしない)を、実際のクライアント経由で確かめる。
"""

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from opensearchpy import OpenSearch
from opensearchpy.exceptions import (
    ConnectionError as OpenSearchConnectionError,
)
from opensearchpy.exceptions import (
    ConnectionTimeout,
    NotFoundError,
    RequestError,
    TransportError,
)

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.infrastructure.opensearch import (
    OpenSearchRepository,
    RecordFilter,
    RepositorySettings,
    SortKey,
)

Operation = Callable[[OpenSearchRepository], object]


def scan_operation(repository: OpenSearchRepository) -> object:
    with repository.scan(RecordFilter(), sort=[SortKey("document_id")]) as pages:
        return list(pages)


OPERATIONS: dict[str, Operation] = {
    "fetch": lambda r: r.fetch("a"),
    "create": lambda r: r.create("a", {}),
    "replace_if_unchanged": lambda r: r.replace_if_unchanged("a", {}, seq_no=0, primary_term=1),
    "delete_if_unchanged": lambda r: r.delete_if_unchanged("a", seq_no=0, primary_term=1),
    "list_records": lambda r: r.list_records(RecordFilter(), [], limit=1),
    "scan": scan_operation,
    "delete_ids": lambda r: r.delete_ids(["a"]),
}

CLUSTER_WIDE_FAILURES = {
    "connection_error": OpenSearchConnectionError("N/A", "refused", Exception("x")),
    "connection_timeout": ConnectionTimeout("TIMEOUT", "timed out", Exception("x")),
    "http_429": TransportError(429, "es_rejected_execution_exception", {}),
    "http_500": TransportError(500, "x", {}),
    "http_503": TransportError(503, "x", {}),
    "cluster_block_exception": TransportError(
        403, "x", {"error": {"type": "cluster_block_exception"}}
    ),
    "circuit_breaking_exception": TransportError(
        429, "x", {"error": {"type": "circuit_breaking_exception"}}
    ),
    "index_not_found_exception": NotFoundError(
        404, "x", {"error": {"type": "index_not_found_exception"}}
    ),
}


@pytest.fixture
def repository(real_client: OpenSearch) -> OpenSearchRepository:
    return OpenSearchRepository(real_client, "loreley-jobs")


@pytest.mark.parametrize("operation", OPERATIONS.values(), ids=OPERATIONS.keys())
@pytest.mark.parametrize("error", CLUSTER_WIDE_FAILURES.values(), ids=CLUSTER_WIDE_FAILURES.keys())
def test_every_operation_raises_store_unavailable_on_a_cluster_wide_failure(
    repository: OpenSearchRepository, transport: MagicMock, operation: Operation, error: Exception
) -> None:
    transport.perform_request.side_effect = error

    with pytest.raises(StoreUnavailableError):
        operation(repository)


@pytest.mark.parametrize(
    "stage_calls", [1, 2, 3], ids=["at-the-pit", "at-the-first-search", "at-the-next-search"]
)
def test_scan_raises_store_unavailable_at_any_stage_and_still_closes_the_pit(
    repository: OpenSearchRepository, transport: MagicMock, stage_calls: int
) -> None:
    hit = {"_id": "a", "_source": {}, "_seq_no": 0, "_primary_term": 1, "sort": ["a"]}
    healthy = [
        {"_shards": {"failed": 0}},  # refresh
        {"pit_id": "PIT"},
        {"pit_id": "PIT", "hits": {"hits": [hit]}},
    ]
    failure = ConnectionTimeout("TIMEOUT", "timed out", Exception("x"))
    transport.perform_request.side_effect = [*healthy[:stage_calls], failure, {"pits": []}]

    with pytest.raises(StoreUnavailableError):
        scan_operation(repository)

    methods_and_urls = [call.args[:2] for call in transport.perform_request.call_args_list]
    has_pit = stage_calls >= 2
    assert (("DELETE", "/_search/point_in_time") in methods_and_urls) is has_pit


def test_an_unexpected_4xx_is_an_unexpected_response_for_every_operation(
    repository: OpenSearchRepository, transport: MagicMock
) -> None:
    transport.perform_request.side_effect = RequestError(
        400, "mapper_parsing_exception", {"error": {"type": "mapper_parsing_exception"}}
    )

    for operation in OPERATIONS.values():
        with pytest.raises(StoreUnexpectedResponseError) as excinfo:
            operation(repository)
        assert excinfo.value.error_type == "mapper_parsing_exception"


def test_a_failure_on_one_batch_of_a_bulk_delete_raises_and_a_retry_of_all_ids_is_safe(
    real_client: OpenSearch, transport: MagicMock
) -> None:
    repository = OpenSearchRepository(
        real_client, "loreley-jobs", RepositorySettings(bulk_delete_batch_size=1)
    )
    transport.perform_request.side_effect = [
        {"errors": False, "items": [{"delete": {"_id": "a", "status": 200, "result": "deleted"}}]},
        ConnectionTimeout("TIMEOUT", "timed out", Exception("x")),
    ]

    with pytest.raises(StoreUnavailableError):
        repository.delete_ids(["a", "b"])


def test_a_bulk_item_blocked_by_the_cluster_is_a_cluster_wide_failure_not_a_partial_one(
    repository: OpenSearchRepository, transport: MagicMock
) -> None:
    item = {
        "delete": {
            "_id": "a",
            "status": 403,
            "error": {"type": "cluster_block_exception", "reason": "SENTINEL-REASON"},
        }
    }
    transport.perform_request.return_value = {"errors": True, "items": [item]}

    with pytest.raises(StoreUnavailableError) as excinfo:
        repository.delete_ids(["a"])

    assert excinfo.value.reason == "cluster_block_exception"
    assert "SENTINEL-REASON" not in str(excinfo.value)


def test_bulk_items_rejected_by_a_busy_node_are_partial_failures_by_id(
    repository: OpenSearchRepository, transport: MagicMock
) -> None:
    items = [
        {"delete": {"_id": "a", "status": 200, "result": "deleted"}},
        {"delete": {"_id": "b", "status": 404, "result": "not_found"}},
        {
            "delete": {
                "_id": "c",
                "status": 429,
                "error": {"type": "es_rejected_execution_exception"},
            }
        },
        {"delete": {"_id": "d", "status": 503, "error": {"type": "unavailable_shards_exception"}}},
    ]
    transport.perform_request.return_value = {"errors": True, "items": items}

    result = repository.delete_ids(["a", "b", "c", "d"])

    assert result.failed_ids == ("c", "d")
