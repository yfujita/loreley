"""B 9.2 の写像表の全行と、送信の失敗を、EP 経由で確かめる(C 11章 1・2)。

`tests/admin/crawler_mapping/` は `translate` を直接呼ぶ。ここは、リクエストから応答までを通して、
EP ごとの Crawler の操作・`lock_state`・`requested`・項目名の写しが、表のとおりになることを見る。
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from loreley_api.admin.crawler_mapping import CrawlerOperation
from loreley_api.infrastructure.crawler_client import (
    CrawlerContractViolation,
    CrawlerRejected,
    CrawlerResult,
    CrawlerTransportFailed,
)
from tests.admin.crawler_mapping.mapping_rows import ROWS
from tests.admin.factories import ADMIN_PREFIX
from tests.admin.write_requests import register_body, seed_lock, update_body
from tests.fakes.fake_crawler_client import FakeCrawlerClient
from tests.fakes.in_memory_readers import InMemoryReaders

SOURCES = f"{ADMIN_PREFIX}/sources"

# 操作 → その EP へのリクエスト(`ROWS` の想定どおり、`requested` の指定は `force_delete=true`・
# `rewrite_mode=false`。`ttl` の違反は `ttl_seconds` の名前で返るので、秒で送る)。
SEND: dict[CrawlerOperation, Callable[[TestClient], Response]] = {
    CrawlerOperation.REGISTER_SOURCE: lambda client: client.post(
        SOURCES, json=register_body(ttl_days=..., ttl_seconds=86_400)
    ),
    CrawlerOperation.UPDATE_SOURCE: lambda client: client.put(
        f"{SOURCES}/docs", json=update_body(ttl_days=..., ttl_seconds=86_400)
    ),
    CrawlerOperation.START_DELETE_JOB: lambda client: client.post(f"{SOURCES}/docs/delete-jobs"),
    CrawlerOperation.START_CRAWL: lambda client: client.post(
        f"{SOURCES}/docs/crawl-jobs", json={"force_delete": True, "rewrite_mode": False}
    ),
    CrawlerOperation.CANCEL_JOB: lambda client: client.post(f"{ADMIN_PREFIX}/jobs/job-1/cancel"),
    CrawlerOperation.RELEASE_LOCK: lambda client: client.delete(f"{SOURCES}/docs/lock"),
}


def error_of(response: Response) -> tuple[int, str, bool, Any]:
    error = response.json()["error"]
    return response.status_code, error["code"], error["retryable"], error.get("details")


def test_every_operation_has_an_endpoint_to_send_it() -> None:
    assert set(SEND) == set(CrawlerOperation)


@pytest.mark.parametrize(
    ("operation", "crawler_response", "expected"),
    ROWS,
    ids=[f"{op.value}-{r.status}-{r.code}" for op, r, _ in ROWS],
)
def test_each_row_of_the_crawler_mapping_table_holds_through_the_endpoint(
    client: TestClient,
    crawler: FakeCrawlerClient,
    readers: InMemoryReaders,
    operation: CrawlerOperation,
    crawler_response: CrawlerRejected,
    expected: tuple[Any, ...],
) -> None:
    seed_lock(readers, "held_crawl")
    crawler.behavior.inject(operation.value, crawler_response)

    response = SEND[operation](client)

    status, code, retryable, details = expected
    assert error_of(response) == (status, code, retryable, details)
    # 1 回だけ送った(再送しない)。
    assert [request.operation for request in crawler.requests] == [operation.value]


TRANSPORT_FAILURES: list[tuple[CrawlerResult, tuple[int, str, bool, Any]]] = [
    (
        CrawlerTransportFailed("before_send", "connection_failed"),
        (503, "crawler_unreachable", True, None),
    ),
    (
        CrawlerTransportFailed("before_send", "name_resolution"),
        (503, "crawler_unreachable", True, None),
    ),
    (
        CrawlerTransportFailed("before_send", "connect_timeout"),
        (503, "crawler_unreachable", True, None),
    ),
    (
        CrawlerTransportFailed("after_send", "response_timeout"),
        (504, "crawler_response_lost", False, {"outcome_unknown": True}),
    ),
    (
        CrawlerTransportFailed("after_send", "connection_lost"),
        (504, "crawler_response_lost", False, {"outcome_unknown": True}),
    ),
    (CrawlerContractViolation("redirect", 307), (502, "crawler_error", False, None)),
    (CrawlerContractViolation("malformed_body", 200), (502, "crawler_error", False, None)),
    (CrawlerContractViolation("unexpected_status", 204), (502, "crawler_error", False, None)),
]


@pytest.mark.parametrize("operation", list(CrawlerOperation))
@pytest.mark.parametrize(
    ("failure", "expected"),
    TRANSPORT_FAILURES,
    ids=[f"{type(f).__name__}-{getattr(f, 'reason', '')}" for f, _ in TRANSPORT_FAILURES],
)
def test_a_failure_of_the_crawler_call_is_the_documented_error_for_every_endpoint(
    client: TestClient,
    crawler: FakeCrawlerClient,
    readers: InMemoryReaders,
    operation: CrawlerOperation,
    failure: CrawlerResult,
    expected: tuple[int, str, bool, Any],
) -> None:
    crawler.behavior.inject(operation.value, failure)

    response = SEND[operation](client)

    assert error_of(response) == expected
    assert [request.operation for request in crawler.requests] == [operation.value]
    # 書き込み系だけが失敗する。OpenSearch の読み取りは起きない(`lock_state` は 409 のときだけ)。
    assert readers.behavior.calls == []


def test_a_crawler_failure_does_not_stop_the_read_endpoints(
    client: TestClient, crawler: FakeCrawlerClient, readers: InMemoryReaders
) -> None:
    """Crawler が落ちていても、読み取り系の EP は応答する(B 2.6・10章)。"""
    readers.put_source("docs", connector_type="file_system", status="active")
    readers.refresh_search()
    crawler.behavior.inject(
        "start_crawl", CrawlerTransportFailed("before_send", "connection_failed"), times=None
    )

    write = SEND[CrawlerOperation.START_CRAWL](client)
    read = client.get(f"{SOURCES}/docs")

    assert write.status_code == 503
    assert read.status_code == 200
