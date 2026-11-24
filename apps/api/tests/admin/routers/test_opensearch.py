"""EP-12 `GET /opensearch/cluster`(アプリ全体。切り詰め・正規化・503)。"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from loreley_api.admin.base.constants import CLUSTER_INDEX_LIMIT
from loreley_api.infrastructure.opensearch import ClusterSnapshot
from tests.admin.factories import ADMIN_PREFIX
from tests.fakes.in_memory_readers import STORE_UNAVAILABLE, InMemoryReaders

CLUSTER = f"{ADMIN_PREFIX}/opensearch/cluster"

HEALTH: dict[str, Any] = {
    "cluster_name": "loreley",
    "status": "yellow",
    "number_of_nodes": 1,
    "active_shards": 1,
    "relocating_shards": 0,
    "initializing_shards": 0,
    "unassigned_shards": 1,
}


def snapshot(
    *, indices: tuple[dict[str, Any], ...] = (), shards: tuple[dict[str, Any], ...] = ()
) -> ClusterSnapshot:
    return ClusterSnapshot(HEALTH, indices, shards, ({"name": "node-1"},))


def test_the_response_is_normalized_in_the_documented_shape(
    readers: InMemoryReaders, client: TestClient
) -> None:
    readers.cluster_snapshot = snapshot(
        indices=(
            {"index": "loreley-documents-000001", "health": "YELLOW", "docs.count": "12846"},
            {"index": "closed", "health": "green", "docs.count": None},
        ),
        shards=(
            {
                "index": "loreley-documents-000001",
                "shard": "0",
                "prirep": "p",
                "state": "STARTED",
                "node": "node-1",
            },
            {
                "index": "loreley-documents-000001",
                "shard": "0",
                "prirep": "r",
                "state": "UNASSIGNED",
                "node": None,
            },
            {
                "index": "only-in-shards",
                "shard": "0",
                "prirep": "p",
                "state": "STARTED",
                "node": "node-1",
            },
        ),
    )

    response = client.get(CLUSTER)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert list(body) == [
        "fetched_at",
        "cluster",
        "nodes",
        "indices",
        "shards",
        "truncated",
        "total_indices",
    ]
    assert body["fetched_at"] == "2026-11-24T00:00:00.000Z"
    assert body["cluster"]["node_count"] == 1
    assert body["indices"] == [
        {"name": "loreley-documents-000001", "status": "yellow", "document_count": 12846},
        {"name": "closed", "status": "green", "document_count": None},
        {"name": "only-in-shards", "status": None, "document_count": None},
    ]
    assert [(s["role"], s["state"], s["node"]) for s in body["shards"][:2]] == [
        ("primary", "started", "node-1"),
        ("replica", "unassigned", None),
    ]
    assert (body["truncated"], body["total_indices"]) == (False, 3)


def test_more_than_the_limit_of_indices_is_truncated_with_the_total(
    readers: InMemoryReaders, client: TestClient
) -> None:
    indices = tuple(
        {"index": f"index-{number:04d}", "health": "green", "docs.count": "1"}
        for number in range(CLUSTER_INDEX_LIMIT + 1)
    )
    readers.cluster_snapshot = snapshot(
        indices=(*indices, {"index": "the-red-one", "health": "red", "docs.count": "1"})
    )

    body = client.get(CLUSTER).json()

    assert len(body["indices"]) == CLUSTER_INDEX_LIMIT
    assert body["indices"][0]["name"] == "the-red-one"
    assert (body["truncated"], body["total_indices"]) == (True, CLUSTER_INDEX_LIMIT + 2)


def test_a_failed_read_is_a_503(readers: InMemoryReaders, client: TestClient) -> None:
    readers.behavior.inject("cluster.read", STORE_UNAVAILABLE)

    response = client.get(CLUSTER)

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "unavailable",
        "message": "the data store is unavailable",
        "retryable": True,
    }


def test_a_response_of_an_unexpected_shape_is_a_503(
    readers: InMemoryReaders, client: TestClient
) -> None:
    readers.cluster_snapshot = ClusterSnapshot({**HEALTH, "status": None}, (), (), ())

    assert client.get(CLUSTER).status_code == 503


def test_an_unknown_query_is_a_400(client: TestClient) -> None:
    response = client.get(f"{CLUSTER}?page=2")

    assert response.status_code == 400
    assert response.json()["error"]["details"]["errors"] == [
        {"field": "page", "reason": "unknown_field"}
    ]


@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_the_cluster_accepts_only_get(client: TestClient, method: str) -> None:
    assert getattr(client, method)(CLUSTER).status_code == 405
