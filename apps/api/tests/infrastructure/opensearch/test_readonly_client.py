"""許可リストのクライアント(D 4.8。C 2.3・3.4)。"""

import inspect

import pytest

from loreley_api.infrastructure.opensearch import ReadOnlyOpenSearch
from tests.fakes.fake_opensearch_client import FakeOpenSearchClient

PUBLIC_METHODS = {
    "search",
    "msearch",
    "mget",
    "cluster_health",
    "cat_indices",
    "cat_shards",
    "cat_nodes",
}


def test_the_public_methods_are_the_seven_allowed_apis() -> None:
    names = {
        name
        for name, member in inspect.getmembers(ReadOnlyOpenSearch, inspect.isfunction)
        if not name.startswith("_")
    }

    assert names == PUBLIC_METHODS


def test_no_public_method_accepts_arbitrary_arguments() -> None:
    """`**kwargs`・`*args` を素通ししない(許可した API に任意の引数を渡せない)。"""
    for name in PUBLIC_METHODS:
        parameters = inspect.signature(getattr(ReadOnlyOpenSearch, name)).parameters.values()
        kinds = {parameter.kind for parameter in parameters}
        assert inspect.Parameter.VAR_KEYWORD not in kinds, name
        assert inspect.Parameter.VAR_POSITIONAL not in kinds, name


def test_the_raw_client_is_not_exposed_as_a_public_attribute() -> None:
    client = ReadOnlyOpenSearch(FakeOpenSearchClient())

    assert [name for name in vars(client) if not name.startswith("_")] == []


def test_search_forwards_the_index_and_body(fake_client: FakeOpenSearchClient) -> None:
    fake_client.script("search", {"ok": 1})
    readonly = ReadOnlyOpenSearch(fake_client)

    assert readonly.search(index="i", body={"size": 0}) == {"ok": 1}

    [request] = fake_client.requests
    assert (request.operation, request.index, request.body) == ("search", "i", {"size": 0})
    assert request.query_params == {}


def test_msearch_forwards_the_body_without_an_index(fake_client: FakeOpenSearchClient) -> None:
    fake_client.script("msearch", {"responses": []})
    body = [{"index": "i"}, {"size": 0}]

    ReadOnlyOpenSearch(fake_client).msearch(body=body)

    [request] = fake_client.requests
    assert (request.operation, request.index, request.body) == ("msearch", None, body)


def test_mget_puts_the_ids_in_the_body_not_the_path(fake_client: FakeOpenSearchClient) -> None:
    fake_client.script("mget", {"docs": []})

    ReadOnlyOpenSearch(fake_client).mget(
        index="i", ids=["a/b", "c?d", "e%f"], source_includes=["x", "y"]
    )

    [request] = fake_client.requests
    assert request.index == "i"
    assert request.body == {"ids": ["a/b", "c?d", "e%f"]}
    assert request.query_params == {"_source_includes": ["x", "y"]}


def test_mget_reads_all_fields_by_default(fake_client: FakeOpenSearchClient) -> None:
    fake_client.script("mget", {"docs": []})

    ReadOnlyOpenSearch(fake_client).mget(index="i", ids=["a"])

    assert fake_client.requests[0].query_params == {}


def test_mget_can_skip_the_source_for_an_existence_check(
    fake_client: FakeOpenSearchClient,
) -> None:
    fake_client.script("mget", {"docs": []})

    ReadOnlyOpenSearch(fake_client).mget(index="i", ids=["a"], include_source=False)

    assert fake_client.requests[0].query_params == {"_source": False}


def test_cluster_health_has_no_wait_arguments(fake_client: FakeOpenSearchClient) -> None:
    fake_client.script("cluster.health", {"status": "green"})

    ReadOnlyOpenSearch(fake_client).cluster_health()

    assert fake_client.requests[0].query_params == {}


@pytest.mark.parametrize(
    ("method", "operation", "expected_params"),
    [
        (
            "cat_indices",
            "cat.indices",
            {
                "format": "json",
                "h": "index,health,docs.count",
                "bytes": "b",
                "expand_wildcards": "all",
            },
        ),
        (
            "cat_shards",
            "cat.shards",
            {"format": "json", "h": "index,shard,prirep,state,node", "bytes": "b"},
        ),
        ("cat_nodes", "cat.nodes", {"format": "json", "h": "name", "bytes": "b"}),
    ],
)
def test_cat_apis_use_the_fixed_arguments(
    fake_client: FakeOpenSearchClient,
    method: str,
    operation: str,
    expected_params: dict[str, str],
) -> None:
    fake_client.script(operation, [])

    getattr(ReadOnlyOpenSearch(fake_client), method)()

    assert fake_client.requests[0].query_params == expected_params
