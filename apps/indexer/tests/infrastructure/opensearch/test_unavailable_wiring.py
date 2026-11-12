"""全体異常(接続タイムアウト・503)が、アダプタのどのメソッドからも全体異常の例外で出る。

分類器(`classify_failure`)の単体テストとは別に、各メソッドが分類器を通していることを確認する。
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from opensearchpy import OpenSearch
from opensearchpy.exceptions import ConnectionTimeout, TransportError

from loreley_indexer.infrastructure.opensearch import (
    DocumentFilter,
    OpenSearchSearchIndexRepository,
    OpenSearchStore,
    OpenSearchUnavailableError,
    RecordFilter,
    SearchIndexRepository,
    StoreRepository,
)

INSTANT = datetime(2026, 11, 9, tzinfo=UTC)

SEARCH_INDEX_CALLS: dict[str, Callable[[OpenSearchSearchIndexRepository], Any]] = {
    "fetch": lambda r: r.fetch("d1"),
    "fetch_for_deletion": lambda r: r.fetch_for_deletion("d1"),
    "create": lambda r: r.create("d1", {}),
    "replace_if_unchanged": lambda r: r.replace_if_unchanged("d1", {}, seq_no=1, primary_term=1),
    "raise_last_seen_at": lambda r: r.raise_last_seen_at("d1", INSTANT),
    "delete_if_unchanged": lambda r: r.delete_if_unchanged("d1", seq_no=1, primary_term=1),
    "search_document_ids": lambda r: r.search_document_ids(
        DocumentFilter(), page_size=10, after=None
    ),
    "count": lambda r: r.count(DocumentFilter()),
    "count_existing_ids": lambda r: r.count_existing_ids(["d1"]),
    "refresh": lambda r: r.refresh(),
    "delete_by_query": lambda r: r.delete_by_query(DocumentFilter(source_id="s1")),
}

STORE_CALLS: dict[str, Callable[[OpenSearchStore], Any]] = {
    "fetch": lambda s: s.fetch("r1"),
    "list_records": lambda s: s.list_records(RecordFilter(), [], limit=1),
    "save": lambda s: s.save("r1", {}),
    "replace_if_unchanged": lambda s: s.replace_if_unchanged("r1", {}, seq_no=1, primary_term=1),
    "delete": lambda s: s.delete("r1"),
}

CLUSTER_WIDE_FAILURES = [
    pytest.param(ConnectionTimeout("TIMEOUT", "timed out", Exception("x")), id="timeout"),
    pytest.param(TransportError(503, "x", {}), id="http_503"),
]


def test_every_repository_method_is_covered() -> None:
    assert set(SEARCH_INDEX_CALLS) == SearchIndexRepository.__abstractmethods__
    assert set(STORE_CALLS) == StoreRepository.__abstractmethods__


@pytest.mark.parametrize("error", CLUSTER_WIDE_FAILURES)
@pytest.mark.parametrize("method_name", SEARCH_INDEX_CALLS)
def test_search_index_methods_raise_unavailable_on_cluster_wide_failure(
    real_client: OpenSearch, transport: MagicMock, method_name: str, error: TransportError
) -> None:
    transport.perform_request.side_effect = error
    repository = OpenSearchSearchIndexRepository(
        real_client,
        "i",
        update_retry_on_conflict=3,
        delete_by_query_client=real_client,
        delete_by_query_timeout_seconds=600.0,
    )

    with pytest.raises(OpenSearchUnavailableError):
        SEARCH_INDEX_CALLS[method_name](repository)


@pytest.mark.parametrize("error", CLUSTER_WIDE_FAILURES)
@pytest.mark.parametrize("method_name", STORE_CALLS)
def test_store_methods_raise_unavailable_on_cluster_wide_failure(
    real_client: OpenSearch, transport: MagicMock, method_name: str, error: TransportError
) -> None:
    transport.perform_request.side_effect = error

    with pytest.raises(OpenSearchUnavailableError):
        STORE_CALLS[method_name](OpenSearchStore(real_client, "i"))


def test_list_records_does_not_search_when_the_refresh_fails(
    real_client: OpenSearch, transport: MagicMock
) -> None:
    transport.perform_request.side_effect = TransportError(503, "x", {})

    with pytest.raises(OpenSearchUnavailableError):
        OpenSearchStore(real_client, "i").list_records(RecordFilter(), [], limit=1)

    requested_urls = [call.args[1] for call in transport.perform_request.call_args_list]
    assert requested_urls == ["/i/_refresh"]
