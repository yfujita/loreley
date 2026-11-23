"""本物の `opensearchpy.OpenSearch` の下(トランスポート)を差し替えて、実際の HTTP 要求を確かめる。

`ReadOnlyOpenSearch` の 7 メソッドが、期待どおりの HTTP メソッド・パス・パラメーターで 1 回だけ
呼ぶこと(許可リストの名前が、生のクライアントの別の API に結び付いていないこと)。外部には
接続しない(`perform_request` を差し替える)。偽のクライアントを使うテストでは、ここは確かめられない。
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import pytest
from opensearchpy import OpenSearch

from loreley_api.infrastructure.opensearch import ReadOnlyOpenSearch


@dataclass(frozen=True)
class SentRequest:
    method: str
    path: str
    params: Mapping[str, str]
    body: object


class RecordingTransport:
    def __init__(self) -> None:
        self.sent: list[SentRequest] = []

    def perform_request(
        self,
        method: str,
        url: str,
        params: Mapping[str, object] | None = None,
        body: object = None,
        headers: object = None,
        **_: object,
    ) -> object:
        # パラメーターの値は、生のクライアントが bytes にして渡す。
        decoded = {
            name: value.decode() if isinstance(value, bytes) else str(value)
            for name, value in (params or {}).items()
        }
        self.sent.append(SentRequest(method, url, decoded, body))
        return {}


@pytest.fixture
def transport() -> RecordingTransport:
    return RecordingTransport()


@pytest.fixture
def readonly(transport: RecordingTransport) -> ReadOnlyOpenSearch:
    raw_client = OpenSearch(hosts=["http://opensearch.invalid:9200"])
    raw_client.transport.perform_request = transport.perform_request
    return ReadOnlyOpenSearch(raw_client)


def test_search_posts_the_body_to_the_index_search_path(
    readonly: ReadOnlyOpenSearch, transport: RecordingTransport
) -> None:
    readonly.search(index="idx", body={"size": 1})

    assert transport.sent == [SentRequest("POST", "/idx/_search", {}, {"size": 1})]


def test_msearch_posts_the_header_and_body_lines_to_the_msearch_path(
    readonly: ReadOnlyOpenSearch, transport: RecordingTransport
) -> None:
    readonly.msearch(body=[{"index": "idx"}, {"size": 0}])

    assert transport.sent == [
        SentRequest("POST", "/_msearch", {}, '{"index":"idx"}\n{"size":0}\n'),
    ]


def test_mget_puts_the_ids_in_the_body_not_in_the_path(
    readonly: ReadOnlyOpenSearch, transport: RecordingTransport
) -> None:
    readonly.mget(index="idx", ids=["a/b", "c"], source_includes=["x", "y"])

    assert transport.sent == [
        SentRequest("POST", "/idx/_mget", {"_source_includes": "x,y"}, {"ids": ["a/b", "c"]}),
    ]


def test_mget_without_source_asks_for_no_source(
    readonly: ReadOnlyOpenSearch, transport: RecordingTransport
) -> None:
    readonly.mget(index="idx", ids=["a"], include_source=False)

    assert transport.sent == [
        SentRequest("POST", "/idx/_mget", {"_source": "false"}, {"ids": ["a"]}),
    ]


def test_mget_without_a_field_list_has_no_source_parameter(
    readonly: ReadOnlyOpenSearch, transport: RecordingTransport
) -> None:
    readonly.mget(index="idx", ids=["a"])

    assert transport.sent == [SentRequest("POST", "/idx/_mget", {}, {"ids": ["a"]})]


@pytest.mark.parametrize(
    ("call", "path", "params"),
    [
        (lambda readonly: readonly.cluster_health(), "/_cluster/health", {}),
        (
            lambda readonly: readonly.cat_indices(),
            "/_cat/indices",
            {
                "format": "json",
                "h": "index,health,docs.count",
                "bytes": "b",
                "expand_wildcards": "all",
            },
        ),
        (
            lambda readonly: readonly.cat_shards(),
            "/_cat/shards",
            {"format": "json", "h": "index,shard,prirep,state,node", "bytes": "b"},
        ),
        (
            lambda readonly: readonly.cat_nodes(),
            "/_cat/nodes",
            {"format": "json", "h": "name", "bytes": "b"},
        ),
    ],
)
def test_the_cluster_reads_use_get_with_the_fixed_parameters(
    readonly: ReadOnlyOpenSearch,
    transport: RecordingTransport,
    call: Callable[[ReadOnlyOpenSearch], object],
    path: str,
    params: dict[str, str],
) -> None:
    call(readonly)

    assert transport.sent == [SentRequest("GET", path, params, None)]
