"""偽の生クライアントが、許可リスト外の呼び出しで失敗すること(C 11章 8 (b))。"""

from collections.abc import Callable

import pytest

from tests.fakes.fake_opensearch_client import (
    FakeOpenSearchClient,
    ForbiddenOpenSearchCall,
    UnscriptedOpenSearchCall,
)


@pytest.mark.parametrize(
    "call",
    [
        lambda client: client.index(index="x", body={}),
        lambda client: client.create(index="x", id="1", body={}),
        lambda client: client.update(index="x", id="1", body={}),
        lambda client: client.delete(index="x", id="1"),
        lambda client: client.bulk(body=[]),
        lambda client: client.delete_by_query(index="x", body={}),
        lambda client: client.update_by_query(index="x", body={}),
        lambda client: client.reindex(body={}),
        lambda client: client.get(index="x", id="1"),
        lambda client: client.count(index="x"),
        lambda client: client.scroll(scroll_id="1"),
        lambda client: client.create_pit(index="x"),
        lambda client: client.indices.refresh(index="x"),
        lambda client: client.indices.get(index="x"),
        lambda client: client.indices.create(index="x"),
        lambda client: client.cluster.put_settings(body={}),
        lambda client: client.cluster.state(),
        lambda client: client.cat.health(),
        lambda client: client.transport.perform_request("POST", "/x"),
    ],
)
def test_a_call_outside_the_allow_list_fails(
    call: Callable[[FakeOpenSearchClient], object],
) -> None:
    client = FakeOpenSearchClient()

    with pytest.raises(ForbiddenOpenSearchCall):
        call(client)


def test_the_failure_is_not_an_exception_so_a_reader_cannot_swallow_it() -> None:
    assert not issubclass(ForbiddenOpenSearchCall, Exception)
    assert not issubclass(UnscriptedOpenSearchCall, Exception)


def test_an_allowed_call_without_a_script_fails() -> None:
    client = FakeOpenSearchClient()

    with pytest.raises(UnscriptedOpenSearchCall):
        client.search(index="x", body={})


@pytest.mark.parametrize(
    ("operation", "call"),
    [
        ("search", lambda client: client.search(index="i", body={"size": 1})),
        ("msearch", lambda client: client.msearch(body=[{"index": "i"}, {}])),
        ("mget", lambda client: client.mget(index="i", body={"ids": ["1"]})),
        ("cluster.health", lambda client: client.cluster.health()),
        ("cat.indices", lambda client: client.cat.indices(format="json")),
        ("cat.shards", lambda client: client.cat.shards(format="json")),
        ("cat.nodes", lambda client: client.cat.nodes(format="json")),
    ],
)
def test_an_allowed_call_returns_the_script_and_is_recorded(
    operation: str, call: Callable[[FakeOpenSearchClient], object]
) -> None:
    client = FakeOpenSearchClient()
    client.script(operation, {"scripted": True})

    assert call(client) == {"scripted": True}
    assert [request.operation for request in client.requests] == [operation]


def test_a_scripted_exception_is_raised_and_each_script_is_used_once() -> None:
    client = FakeOpenSearchClient()
    client.script("search", RuntimeError("boom"))
    client.script("search", {"second": True})

    with pytest.raises(RuntimeError):
        client.search(index="i", body={})
    assert client.search(index="i", body={}) == {"second": True}
    with pytest.raises(UnscriptedOpenSearchCall):
        client.search(index="i", body={})


def test_the_recorded_body_is_a_copy() -> None:
    client = FakeOpenSearchClient()
    client.script("search", {})
    body: dict[str, object] = {"size": 1}

    client.search(index="i", body=body)
    body["size"] = 2

    assert client.requests[0].body == {"size": 1}
