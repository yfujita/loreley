"""アダプタが実際の `OpenSearch` クライアント経由で送るリクエストの形(通信層はモック)。

クライアントのメソッド呼び出し(`client.index(...)` など)が、どの HTTP メソッド・URL・
クエリパラメータになるかを確認する。たとえば `retry_on_conflict` や `conflicts=proceed` が
クエリパラメータとして実際に送られること。実機での挙動(U-31)の確認ではない。

opensearch-py の呼び出し規約に依存する: 通信層の `perform_request` に、HTTP メソッドと URL が
位置引数(`call.args[:2]`)、クエリパラメータと本文が `kwargs["params"]`・`kwargs["body"]` で渡る。
メジャー更新でこのテストが壊れたら、まずリクエスト形そのものが変わっていないかを確認する
(テストの読み取り方だけを直して済ませない)。
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from opensearchpy import OpenSearch

from loreley_indexer.infrastructure.opensearch import (
    DocumentFilter,
    OpenSearchSearchIndexRepository,
    OpenSearchStore,
    RecordFilter,
)

INDEX = "loreley-documents"


DELETE_BY_QUERY_TIMEOUT_SECONDS = 600.0
FOUND_DOCUMENT = {"found": True, "_source": {}, "_seq_no": 0, "_primary_term": 1}


@pytest.fixture
def repository(real_client: OpenSearch) -> OpenSearchSearchIndexRepository:
    return OpenSearchSearchIndexRepository(
        real_client,
        INDEX,
        update_retry_on_conflict=3,
        delete_by_query_client=real_client,
        delete_by_query_timeout_seconds=DELETE_BY_QUERY_TIMEOUT_SECONDS,
    )


def last_request(transport: MagicMock) -> tuple[str, str, dict[str, str]]:
    """直近のリクエストの (HTTP メソッド, URL, クエリパラメータ)。値は文字列にそろえる。"""
    call = transport.perform_request.call_args
    method, url = call.args[:2]
    params = {
        name: value.decode() if isinstance(value, bytes) else str(value)
        for name, value in call.kwargs.get("params", {}).items()
    }
    return method, url, params


def test_fetch_for_deletion_gets_with_only_the_needed_source_fields(
    repository: OpenSearchSearchIndexRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = FOUND_DOCUMENT
    repository.fetch_for_deletion("doc-1")
    assert last_request(transport) == (
        "GET",
        f"/{INDEX}/_doc/doc-1",
        {"_source_includes": "source_id,last_seen_at"},
    )


def test_create_puts_with_op_type_create(
    repository: OpenSearchSearchIndexRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = {"result": "created", "_seq_no": 0, "_primary_term": 1}
    repository.create("doc-1", {"title": "t"})
    assert last_request(transport) == ("PUT", f"/{INDEX}/_doc/doc-1", {"op_type": "create"})
    assert transport.perform_request.call_args.kwargs["body"] == {"title": "t"}


def test_replace_puts_with_the_version_conditions(
    repository: OpenSearchSearchIndexRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = {"result": "updated", "_seq_no": 8, "_primary_term": 2}
    repository.replace_if_unchanged("doc-1", {}, seq_no=7, primary_term=2)
    assert last_request(transport) == (
        "PUT",
        f"/{INDEX}/_doc/doc-1",
        {"if_seq_no": "7", "if_primary_term": "2"},
    )


def test_document_id_is_url_encoded(
    repository: OpenSearchSearchIndexRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = FOUND_DOCUMENT
    repository.fetch("a/b c")
    assert last_request(transport)[:2] == ("GET", f"/{INDEX}/_doc/a%2Fb%20c")


def test_last_seen_at_update_posts_to_update_with_retry_on_conflict(
    repository: OpenSearchSearchIndexRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = {"result": "updated"}
    repository.raise_last_seen_at("doc-1", datetime(2026, 11, 9, tzinfo=UTC))
    assert last_request(transport) == (
        "POST",
        f"/{INDEX}/_update/doc-1",
        {"retry_on_conflict": "3"},
    )


def test_delete_if_unchanged_deletes_with_the_version_conditions(
    repository: OpenSearchSearchIndexRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = {"result": "deleted"}
    repository.delete_if_unchanged("doc-1", seq_no=7, primary_term=2)
    assert last_request(transport) == (
        "DELETE",
        f"/{INDEX}/_doc/doc-1",
        {"if_seq_no": "7", "if_primary_term": "2"},
    )


def test_delete_by_query_posts_with_conflicts_proceed(
    repository: OpenSearchSearchIndexRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = {"deleted": 0}
    repository.delete_by_query(DocumentFilter(source_id="s1"))
    method, url, params = last_request(transport)
    assert (method, url) == ("POST", f"/{INDEX}/_delete_by_query")
    assert params["conflicts"] == "proceed"


def test_delete_by_query_sends_its_own_request_timeout(
    repository: OpenSearchSearchIndexRepository, transport: MagicMock
) -> None:
    """通常のリクエストの timeout(`os_request_timeout_seconds`)とは別の、長い値を渡す(P4)。

    `request_timeout` は通信層でクライアント側の待ち時間として取り除かれる(サーバ側の
    操作の timeout である `timeout` クエリパラメータとは別)。
    """
    transport.perform_request.return_value = {"deleted": 0}
    repository.delete_by_query(DocumentFilter(source_id="s1"))
    _, _, params = last_request(transport)
    assert params == {"conflicts": "proceed", "request_timeout": "600.0"}
    assert "timeout" not in params


def test_other_requests_carry_no_request_timeout_of_their_own(
    repository: OpenSearchSearchIndexRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = {"count": 0}
    repository.count(DocumentFilter(source_id="s1"))
    assert "request_timeout" not in last_request(transport)[2]


def test_count_posts_to_count(
    repository: OpenSearchSearchIndexRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = {"count": 0}
    repository.count(DocumentFilter(source_id="s1"))
    assert last_request(transport) == ("POST", f"/{INDEX}/_count", {})


def test_search_and_refresh_requests(
    repository: OpenSearchSearchIndexRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = {"hits": {"hits": []}}
    repository.search_document_ids(DocumentFilter(), page_size=10, after=None)
    assert last_request(transport) == ("POST", f"/{INDEX}/_search", {})

    transport.perform_request.return_value = {}
    repository.refresh()
    assert last_request(transport) == ("POST", f"/{INDEX}/_refresh", {})


def test_store_requests(real_client: OpenSearch, transport: MagicMock) -> None:
    store = OpenSearchStore(real_client, "loreley-deletions")
    transport.perform_request.return_value = {"result": "created", "_seq_no": 0, "_primary_term": 1}
    store.save("r1", {})
    assert last_request(transport) == ("PUT", "/loreley-deletions/_doc/r1", {})

    transport.perform_request.return_value = {"result": "deleted"}
    store.delete("r1")
    assert last_request(transport) == ("DELETE", "/loreley-deletions/_doc/r1", {})

    responses: list[dict[str, Any]] = [{}, {"hits": {"hits": []}}]
    transport.perform_request.side_effect = responses
    store.list_records(RecordFilter(), [], limit=1)
    methods_and_urls = [call.args[:2] for call in transport.perform_request.call_args_list[-2:]]
    assert methods_and_urls == [
        ("POST", "/loreley-deletions/_refresh"),
        ("POST", "/loreley-deletions/_search"),
    ]
