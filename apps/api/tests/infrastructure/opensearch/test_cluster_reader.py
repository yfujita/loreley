"""ClusterReader(R-12。`cluster.health`・`cat.*`)。"""

import copy

import pytest
from opensearchpy.exceptions import ConnectionTimeout, TransportError

from loreley_api.common.results import Failed, Ok
from loreley_api.infrastructure.opensearch import (
    ClusterSnapshot,
    OpenSearchClusterReader,
    ReadOnlyOpenSearch,
)
from tests.fakes.fake_opensearch_client import FakeOpenSearchClient

HEALTH = {
    "cluster_name": "loreley",
    "status": "yellow",
    "number_of_nodes": 1,
    "active_shards": 4,
    "relocating_shards": 0,
    "initializing_shards": 0,
    "unassigned_shards": 1,
}
INDICES = [{"index": "loreley-jobs", "health": "green", "docs.count": "12"}]
SHARDS = [
    {"index": "loreley-jobs", "shard": "0", "prirep": "p", "state": "STARTED", "node": "n1"},
    {"index": "loreley-jobs", "shard": "0", "prirep": "r", "state": "UNASSIGNED", "node": None},
]
NODES = [{"name": "n1"}]

OPERATIONS = ("cluster.health", "cat.indices", "cat.shards", "cat.nodes")


@pytest.fixture
def reader(readonly: ReadOnlyOpenSearch) -> OpenSearchClusterReader:
    return OpenSearchClusterReader(readonly)


GOOD_RESPONSES: dict[str, object] = {
    "cluster.health": HEALTH,
    "cat.indices": INDICES,
    "cat.shards": SHARDS,
    "cat.nodes": NODES,
}


def script_responses(fake_client: FakeOpenSearchClient, **overrides: object) -> None:
    """4 つの呼び出しの台本。`overrides` は、操作名の `.` を `_` にしたキーで差し替える。"""
    for operation, response in GOOD_RESPONSES.items():
        outcome = overrides.get(operation.replace(".", "_"), response)
        fake_client.script(operation, copy.deepcopy(outcome))


def test_read_returns_the_responses_as_they_are(
    reader: OpenSearchClusterReader, fake_client: FakeOpenSearchClient
) -> None:
    script_responses(fake_client)

    result = reader.read()

    assert result == Ok(
        ClusterSnapshot(
            health=HEALTH, indices=tuple(INDICES), shards=tuple(SHARDS), nodes=tuple(NODES)
        )
    )  # 値は文字列のまま(正規化は derivation)
    assert [request.operation for request in fake_client.requests] == list(OPERATIONS)


@pytest.mark.parametrize("failing_operation", OPERATIONS)
def test_read_stops_at_the_first_failure(
    reader: OpenSearchClusterReader, fake_client: FakeOpenSearchClient, failing_operation: str
) -> None:
    script_responses(
        fake_client, **{failing_operation.replace(".", "_"): TransportError(503, "x", {})}
    )

    assert reader.read() == Failed("unavailable", "store", "TransportError")
    # 失敗した呼び出しまでで打ち切る(以降は呼ばない)。
    called = [request.operation for request in fake_client.requests]
    assert called == list(OPERATIONS[: OPERATIONS.index(failing_operation) + 1])


def test_read_reports_a_timeout(
    reader: OpenSearchClusterReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("cluster.health", ConnectionTimeout("TIMEOUT", "x", None))

    assert reader.read() == Failed("timeout", "store", "ConnectionTimeout")


@pytest.mark.parametrize("missing", sorted(HEALTH))
def test_read_fails_when_a_health_field_is_missing(
    reader: OpenSearchClusterReader, fake_client: FakeOpenSearchClient, missing: str
) -> None:
    fake_client.script("cluster.health", {k: v for k, v in HEALTH.items() if k != missing})

    assert reader.read() == Failed("unavailable", "store", "ResponseShapeError")


@pytest.mark.parametrize(
    ("operation", "response"),
    [
        ("cluster.health", []),
        ("cluster.health", "green"),
        ("cat.indices", {"index": "x"}),
        ("cat.indices", ["not an object"]),
        ("cat.indices", [{"index": "x", "health": "green"}]),  # `docs.count` がない
        ("cat.shards", [{"index": "x", "shard": "0", "prirep": "p", "state": "STARTED"}]),
        ("cat.nodes", [{"unexpected": "x"}]),
    ],
)
def test_read_fails_when_a_response_has_an_unexpected_shape(
    reader: OpenSearchClusterReader,
    fake_client: FakeOpenSearchClient,
    operation: str,
    response: object,
) -> None:
    script_responses(fake_client, **{operation.replace(".", "_"): response})

    assert reader.read() == Failed("unavailable", "store", "ResponseShapeError")


def test_read_accepts_empty_cat_responses(
    reader: OpenSearchClusterReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("cluster.health", copy.deepcopy(HEALTH))
    for operation in ("cat.indices", "cat.shards", "cat.nodes"):
        fake_client.script(operation, [])

    assert reader.read() == Ok(ClusterSnapshot(HEALTH, (), (), ()))
