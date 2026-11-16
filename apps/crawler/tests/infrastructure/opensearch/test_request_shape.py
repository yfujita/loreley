"""アダプタが実際の `OpenSearch` クライアント経由で送るリクエストの形(通信層はモック)。

クライアントのメソッド呼び出しが、どの HTTP メソッド・URL・クエリパラメータ・本文になるかを確認する
(`if_seq_no`・`op_type`・PIT・`search_after`・refresh・バルク削除。architecture 12章)。
実機での挙動(CA-U-18)の確認ではない。

opensearch-py の呼び出し規約に依存する: 通信層の `perform_request` に、HTTP メソッドと URL が
位置引数、クエリパラメータと本文が `params`・`body` で渡る。メジャー更新でこのテストが壊れたら、
まずリクエスト形そのものが変わっていないかを確認する(読み取り方だけを直して済ませない)。
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
from opensearchpy import OpenSearch
from opensearchpy.exceptions import ConflictError, ConnectionTimeout
from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.infrastructure.opensearch import (
    LIST_MAX_SIZE,
    AlreadyExists,
    Conflict,
    OpenSearchRepository,
    RecordFilter,
    RepositorySettings,
    SortKey,
)

INDEX = "loreley-jobs"
SETTINGS = RepositorySettings(
    scan_page_size=500,
    scan_pit_keep_alive_seconds=90,
    scan_request_timeout_seconds=45.0,
    bulk_delete_batch_size=2,
)


@pytest.fixture
def repository(real_client: OpenSearch) -> OpenSearchRepository:
    return OpenSearchRepository(real_client, INDEX, SETTINGS)


def requests_of(transport: MagicMock) -> list[tuple[str, str, dict[str, str], Any]]:
    """送ったリクエストすべての (HTTP メソッド, URL, クエリパラメータ, 本文)。"""
    return [
        (
            request.args[0],
            request.args[1],
            {
                name: value.decode() if isinstance(value, bytes) else str(value)
                for name, value in (request.kwargs.get("params") or {}).items()
            },
            request.kwargs.get("body"),
        )
        for request in transport.perform_request.call_args_list
    ]


def test_fetch_gets_the_record_by_id(
    repository: OpenSearchRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = {
        "_source": {"a": 1},
        "_seq_no": 4,
        "_primary_term": 1,
    }

    record = repository.fetch("job-1")

    assert requests_of(transport) == [("GET", f"/{INDEX}/_doc/job-1", {}, None)]
    assert record is not None
    assert (record.seq_no, record.primary_term) == (4, 1)


def test_create_puts_with_op_type_create_and_no_version_condition(
    repository: OpenSearchRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = {"result": "created", "_seq_no": 0, "_primary_term": 1}

    repository.create("lock-s1", {"owner": "a"})

    assert requests_of(transport) == [
        ("PUT", f"/{INDEX}/_doc/lock-s1", {"op_type": "create"}, {"owner": "a"})
    ]


def test_replace_puts_with_the_version_conditions_and_no_op_type(
    repository: OpenSearchRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = {"result": "updated", "_seq_no": 8, "_primary_term": 2}

    repository.replace_if_unchanged("job-1", {"s": 1}, seq_no=7, primary_term=2)

    assert requests_of(transport) == [
        ("PUT", f"/{INDEX}/_doc/job-1", {"if_seq_no": "7", "if_primary_term": "2"}, {"s": 1})
    ]


def test_delete_with_the_version_conditions(
    repository: OpenSearchRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = {"result": "deleted"}

    repository.delete_if_unchanged("lock-s1", seq_no=7, primary_term=2)

    assert requests_of(transport) == [
        ("DELETE", f"/{INDEX}/_doc/lock-s1", {"if_seq_no": "7", "if_primary_term": "2"}, None)
    ]


def test_a_409_on_create_is_already_exists_and_on_replace_is_a_conflict(
    repository: OpenSearchRepository, transport: MagicMock
) -> None:
    transport.perform_request.side_effect = ConflictError(
        409, "x", {"error": {"type": "version_conflict_engine_exception"}}
    )

    assert repository.create("lock-s1", {}) == AlreadyExists()
    assert repository.replace_if_unchanged("lock-s1", {}, seq_no=1, primary_term=1) == Conflict()


def test_list_refreshes_first_and_searches_the_index_with_the_filter_sort_and_size(
    repository: OpenSearchRepository, transport: MagicMock
) -> None:
    transport.perform_request.side_effect = [{"_shards": {"failed": 0}}, {"hits": {"hits": []}}]

    repository.list_records(
        RecordFilter(equals={"record_type": "job"}, exists=("queued_at",)),
        [SortKey("queued_at"), SortKey("job_id", descending=True)],
        limit=50,
    )

    refresh, search = requests_of(transport)
    assert refresh[:2] == ("POST", f"/{INDEX}/_refresh")
    assert search[:2] == ("POST", f"/{INDEX}/_search")
    assert search[2] == {"allow_partial_search_results": "false"}
    assert search[3] == {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"record_type": "job"}},
                    {"exists": {"field": "queued_at"}},
                ],
                "must_not": [],
            }
        },
        "sort": [{"queued_at": "asc"}, {"job_id": "desc"}],
        "size": 50,
        "seq_no_primary_term": True,
    }


@pytest.mark.parametrize("limit", [1, LIST_MAX_SIZE])
def test_list_accepts_the_smallest_and_largest_limits_and_sends_them_as_the_size(
    repository: OpenSearchRepository, transport: MagicMock, limit: int
) -> None:
    transport.perform_request.side_effect = [{"_shards": {"failed": 0}}, {"hits": {"hits": []}}]

    repository.list_records(RecordFilter(), [], limit=limit)

    assert requests_of(transport)[1][3]["size"] == limit


def hit(record_id: str, sort_value: str) -> dict[str, Any]:
    return {
        "_id": record_id,
        "_source": {},
        "_seq_no": 1,
        "_primary_term": 1,
        "sort": [sort_value],
    }


def test_scan_refreshes_then_opens_a_pit_then_pages_with_search_after_then_closes_the_pit(
    repository: OpenSearchRepository, transport: MagicMock
) -> None:
    transport.perform_request.side_effect = [
        {"_shards": {"failed": 0}},  # refresh
        {"pit_id": "PIT-1"},  # create_pit
        {"pit_id": "PIT-2", "hits": {"hits": [hit("a", "d1"), hit("b", "d2")]}},
        {"pit_id": "PIT-3", "hits": {"hits": [hit("c", "d3")]}},
        {"pit_id": "PIT-3", "hits": {"hits": []}},
        {"pits": []},  # delete_pit
    ]
    record_filter = RecordFilter(equals={"source_id": "s1", "record_type": "skip"})

    with repository.scan(record_filter, sort=[SortKey("document_id")]) as pages:
        read = [[record.id for record in page] for page in pages]

    assert read == [["a", "b"], ["c"]]
    refresh, create_pit, first, second, third, delete_pit = requests_of(transport)
    assert refresh[:2] == ("POST", f"/{INDEX}/_refresh")
    assert create_pit[:3] == (
        "POST",
        f"/{INDEX}/_search/point_in_time",
        {
            "keep_alive": "90s",
            "allow_partial_pit_creation": "false",
            "request_timeout": "45.0",
        },
    )
    expected_query = {
        "bool": {
            "filter": [{"term": {"source_id": "s1"}}, {"term": {"record_type": "skip"}}],
            "must_not": [],
        }
    }
    # PIT を使う検索は、索引名をパスに含めない。1 ページ目は `search_after` なし。
    assert first[:2] == ("POST", "/_search")
    assert first[2] == {"allow_partial_search_results": "false", "request_timeout": "45.0"}
    assert first[3] == {
        "query": expected_query,
        "sort": [{"document_id": "asc"}],
        "size": 500,
        "seq_no_primary_term": True,
        "pit": {"id": "PIT-1", "keep_alive": "90s"},
    }
    # 2 ページ目以降は、直前のページの最後の記録の並べ替えの値を `search_after` に渡し、
    # 応答で変わった PIT の ID を使う。
    assert second[3]["search_after"] == ["d2"]
    assert second[3]["pit"] == {"id": "PIT-2", "keep_alive": "90s"}
    assert third[3]["search_after"] == ["d3"]
    assert delete_pit[:2] == ("DELETE", "/_search/point_in_time")
    assert delete_pit[3] == {"pit_id": ["PIT-3"]}


def test_scan_closes_the_pit_even_when_a_search_fails(
    repository: OpenSearchRepository, transport: MagicMock
) -> None:
    transport.perform_request.side_effect = [
        {"_shards": {"failed": 0}},
        {"pit_id": "PIT-1"},
        ConflictError(409, "x", {}),  # 想定外の応答
        {"pits": []},
    ]

    with (
        pytest.raises(StoreUnexpectedResponseError, match="conflict"),
        repository.scan(RecordFilter(), sort=[SortKey("document_id")]) as pages,
    ):
        list(pages)

    delete_pit = requests_of(transport)[-1]
    assert delete_pit[:2] == ("DELETE", "/_search/point_in_time")
    assert delete_pit[3] == {"pit_id": ["PIT-1"]}  # 失敗時も、開いた PIT を閉じる


def test_a_failure_to_close_the_pit_does_not_change_the_scan_result(
    repository: OpenSearchRepository, transport: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    transport.perform_request.side_effect = [
        {"_shards": {"failed": 0}},
        {"pit_id": "PIT-1"},
        {"pit_id": "PIT-1", "hits": {"hits": [hit("a", "d1")]}},
        {"pit_id": "PIT-1", "hits": {"hits": []}},
        OpenSearchConnectionError("N/A", "SENTINEL-CLOSE-FAILURE", Exception("x")),
    ]

    with repository.scan(RecordFilter(), sort=[SortKey("document_id")]) as pages:
        read = [record.id for page in pages for record in page]

    assert read == ["a"]
    assert "SENTINEL-CLOSE-FAILURE" not in caplog.text
    assert "failed to close the point in time" in caplog.text


def test_scan_does_not_open_a_pit_when_the_refresh_fails(
    repository: OpenSearchRepository, transport: MagicMock
) -> None:
    transport.perform_request.side_effect = ConnectionTimeout("TIMEOUT", "x", Exception("x"))

    with (
        pytest.raises(StoreUnavailableError),
        repository.scan(RecordFilter(), sort=[SortKey("document_id")]),
    ):
        pytest.fail("the scan must not start")

    assert [r[:2] for r in requests_of(transport)] == [("POST", f"/{INDEX}/_refresh")]


def test_an_incomplete_refresh_is_a_cluster_wide_failure(
    repository: OpenSearchRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = {"_shards": {"total": 2, "failed": 1}}

    with pytest.raises(StoreUnavailableError) as excinfo:
        repository.list_records(RecordFilter(), [], limit=10)

    assert excinfo.value.reason == "refresh_incomplete"


def test_bulk_delete_sends_delete_actions_in_batches_of_the_configured_size(
    repository: OpenSearchRepository, transport: MagicMock
) -> None:
    transport.perform_request.return_value = {"errors": False, "items": []}

    repository.delete_ids(["a", "b", "c", "a"])

    bulk_requests = requests_of(transport)
    assert [r[:2] for r in bulk_requests] == [("POST", "/_bulk"), ("POST", "/_bulk")]
    # 重複する ID は 1 回だけ。件数の上限(2)ごとに分ける。本文は改行区切りで、改行で終わる。
    assert bulk_requests[0][3] == (
        f'{{"delete":{{"_index":"{INDEX}","_id":"a"}}}}\n'
        f'{{"delete":{{"_index":"{INDEX}","_id":"b"}}}}\n'
    )
    assert bulk_requests[1][3] == f'{{"delete":{{"_index":"{INDEX}","_id":"c"}}}}\n'


def test_bulk_delete_without_ids_sends_nothing(
    repository: OpenSearchRepository, transport: MagicMock
) -> None:
    repository.delete_ids([])

    assert transport.perform_request.call_args_list == []
