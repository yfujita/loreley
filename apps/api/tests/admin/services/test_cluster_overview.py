"""OpenSearch の状態(EP-12。C 3.4・8.3。B 7.1)。"""

import logging
from typing import Any

import pytest

from loreley_api.admin.base.errors import AdminApiError
from loreley_api.admin.services.cluster_overview import ClusterOverviewService
from loreley_api.infrastructure.opensearch import ClusterSnapshot
from tests.admin.factories import make_admin_dependencies
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_readers import STORE_TIMEOUT, STORE_UNAVAILABLE, InMemoryReaders
from tests.fakes.inline_runner import InlineRunner
from tests.secret_assertions import assert_secret_absent

pytestmark = pytest.mark.anyio

SENTINEL = "SENTINEL-CLUSTER-VALUE"


def make_snapshot(**health_overrides: Any) -> ClusterSnapshot:
    return ClusterSnapshot(
        health={
            "cluster_name": "loreley",
            "status": "yellow",
            "number_of_nodes": 1,
            "active_shards": 1,
            "relocating_shards": 0,
            "initializing_shards": 0,
            "unassigned_shards": 1,
            **health_overrides,
        },
        indices=({"index": "loreley-documents-000001", "health": "yellow", "docs.count": "12846"},),
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
        ),
        nodes=({"name": "node-1"},),
    )


@pytest.fixture
def service(
    readers: InMemoryReaders, fixed_clock: FixedClock, inline_runner: InlineRunner
) -> ClusterOverviewService:
    return make_admin_dependencies(readers, fixed_clock, inline_runner).cluster_overview


async def test_the_example_of_the_spec_is_returned_in_the_documented_shape(
    readers: InMemoryReaders, service: ClusterOverviewService
) -> None:
    readers.cluster_snapshot = make_snapshot()

    response = await service.get_cluster()

    assert response.model_dump(mode="json") == {
        "fetched_at": "2026-11-24T00:00:00.000Z",
        "cluster": {
            "name": "loreley",
            "status": "yellow",
            "node_count": 1,
            "active_shards": 1,
            "relocating_shards": 0,
            "initializing_shards": 0,
            "unassigned_shards": 1,
        },
        "nodes": [{"name": "node-1"}],
        "indices": [
            {"name": "loreley-documents-000001", "status": "yellow", "document_count": 12846}
        ],
        "shards": [
            {
                "index": "loreley-documents-000001",
                "shard": 0,
                "role": "primary",
                "state": "started",
                "node": "node-1",
            },
            {
                "index": "loreley-documents-000001",
                "shard": 0,
                "role": "replica",
                "state": "unassigned",
                "node": None,
            },
        ],
        "truncated": False,
        "total_indices": 1,
    }


async def test_the_fetch_time_is_the_clock_of_the_request(
    readers: InMemoryReaders, service: ClusterOverviewService, fixed_clock: FixedClock
) -> None:
    readers.cluster_snapshot = make_snapshot()
    fixed_clock.advance(seconds=90.5)

    assert (await service.get_cluster()).fetched_at == "2026-11-24T00:01:30.500Z"


@pytest.mark.parametrize("failed", [STORE_UNAVAILABLE, STORE_TIMEOUT])
async def test_a_failed_read_is_a_503_and_never_a_partial_response(
    readers: InMemoryReaders, service: ClusterOverviewService, failed: Any
) -> None:
    readers.cluster_snapshot = make_snapshot()
    readers.behavior.inject("cluster.read", failed)

    with pytest.raises(AdminApiError) as caught:
        await service.get_cluster()

    assert (caught.value.status_code, caught.value.code, caught.value.retryable) == (
        503,
        "unavailable",
        True,
    )


async def test_a_response_of_an_unexpected_shape_is_a_503_and_logs_only_the_class_and_the_reason(
    readers: InMemoryReaders, service: ClusterOverviewService, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    readers.cluster_snapshot = make_snapshot(number_of_nodes=SENTINEL, cluster_name=SENTINEL)

    with pytest.raises(AdminApiError) as caught:
        await service.get_cluster()

    assert (caught.value.status_code, caught.value.code) == (503, "unavailable")
    messages = [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]
    assert messages == [
        "opensearch cluster response has an unexpected shape: "
        "error=ClusterShapeError reason=health_number_of_nodes"
    ]
    assert_secret_absent(SENTINEL, response_text=str(caught.value), records=caplog.records)
    # 元の例外(値を含みうる)を連鎖に残さない。
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


async def test_the_read_goes_through_the_runner_in_the_opensearch_category(
    readers: InMemoryReaders, service: ClusterOverviewService, inline_runner: InlineRunner
) -> None:
    readers.cluster_snapshot = make_snapshot()

    await service.get_cluster()

    assert inline_runner.categories == ["opensearch"]
