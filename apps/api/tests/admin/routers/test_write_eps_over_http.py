"""EP-03〜08 を、実際の Crawler クライアント(`HttpCrawlerClient`)とローカル HTTP スタブで通す。

C 11章 1〜4 の EP 経由の確認。`TestClient` で Admin API を呼び、Crawler 側のスタブが受けた
**生のリクエスト行**(パスのエンコード)・本文・ヘッダー・回数を確かめる。実 Crawler には接続しない。
"""

import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from loreley_api.admin import create_admin_app
from loreley_api.common.http.body import MAX_REQUEST_BODY_BYTES
from loreley_api.common.logging_setup import configure_logging
from loreley_api.infrastructure.crawler_client import CrawlerClientConfig, HttpCrawlerClient
from loreley_api.infrastructure.crawler_client.parsing import RESPONSE_MAX_BYTES
from loreley_api.server import SubAppMount, create_app
from tests.admin.factories import ADMIN_PREFIX, SENTINEL, make_admin_dependencies
from tests.admin.write_requests import (
    crawler_accepted_body,
    crawler_source_body,
    register_body,
    seed_lock,
    update_body,
)
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.fakes.inline_runner import InlineRunner
from tests.fakes.local_http_server import (
    LocalHttpServer,
    StubReply,
    closed_port,
    local_http_server,
)
from tests.secret_assertions import assert_secret_absent

SOURCES = f"{ADMIN_PREFIX}/sources"
JOBS = f"{ADMIN_PREFIX}/jobs"
JSON_HEADERS = {"Content-Type": "application/json"}


def json_reply(status: int, body: dict[str, Any]) -> StubReply:
    return StubReply(status, json.dumps(body).encode(), JSON_HEADERS)


def error_reply(status: int, code: str, **details: Any) -> StubReply:
    error: dict[str, Any] = {"code": code, "message": "fixed", "retryable": False}
    if details:
        error["details"] = details
    return json_reply(status, {"error": error})


@pytest.fixture
def server() -> Iterator[LocalHttpServer]:
    with local_http_server() as stub:
        yield stub


def make_client(
    config: CrawlerClientConfig, readers: InMemoryReaders
) -> tuple[TestClient, HttpCrawlerClient]:
    crawler = HttpCrawlerClient(config)
    deps = make_admin_dependencies(readers, FixedClock(), InlineRunner(), crawler=crawler)
    app = create_app(mounts=[SubAppMount(ADMIN_PREFIX, create_admin_app(deps))])
    return TestClient(app), crawler


@pytest.fixture
def client(server: LocalHttpServer, readers: InMemoryReaders) -> Iterator[TestClient]:
    test_client, crawler = make_client(CrawlerClientConfig(server.url, 3.0, 5.0), readers)
    yield test_client
    crawler.close()


# --- 6 経路: メソッド・パス(生のリクエスト行)・本文・回数 ---

ACCEPTED_DELETE = json_reply(202, crawler_accepted_body("source_delete", with_options=False))
ACCEPTED_CRAWL = json_reply(202, crawler_accepted_body(force_delete=True, rewrite_mode=False))
SOURCE_SAVED = json_reply(201, crawler_source_body())
RELEASED = json_reply(200, {"source_id": "a.b", "released": True, "failed_job_id": None})
CANCELLED = json_reply(200, {"job_id": "x", "status": "cancelled"})


def test_a_registration_sends_one_post_with_the_crawler_units(
    client: TestClient, server: LocalHttpServer
) -> None:
    server.set_default_reply(SOURCE_SAVED)

    response = client.post(SOURCES, json=register_body())

    assert response.status_code == 201
    [received] = server.requests
    assert received.request_line == "POST /sources HTTP/1.1"
    assert received.headers["content-type"] == "application/json"
    assert json.loads(received.body) == {
        "source_id": "docs-share",
        "connector_type": "file_system",
        "connector_config": register_body()["connector_config"],
        "ttl": 2_592_000,
        "ratio_threshold": 0.2,
        "min_delete_count": 10,
        "schedule_cron": "0 3 * * *",
    }


def test_an_update_sends_one_put_to_the_encoded_path_without_the_id_in_the_body(
    client: TestClient, server: LocalHttpServer
) -> None:
    server.set_default_reply(json_reply(200, crawler_source_body("a.b")))

    response = client.put(f"{SOURCES}/a.b", json=update_body(schedule_cron=...))

    assert response.status_code == 200
    [received] = server.requests
    # `.` は `%2E` にする(urllib3 のドットセグメントの除去を避ける。B 2.12)。
    assert received.request_line == "PUT /sources/a%2Eb HTTP/1.1"
    body = json.loads(received.body)
    assert "source_id" not in body
    assert "connector_type" not in body
    assert body["schedule_cron"] is None


def test_a_delete_job_sends_one_post_without_a_body(
    client: TestClient, server: LocalHttpServer
) -> None:
    server.set_default_reply(ACCEPTED_DELETE)

    response = client.post(f"{SOURCES}/a.b/delete-jobs", json={"force_delete": True})

    assert response.status_code == 202
    [received] = server.requests
    assert received.request_line == "POST /sources/a%2Eb/delete-jobs HTTP/1.1"
    # 本文を読まない EP なので、Crawler には何も渡さない。
    assert received.body == b""
    assert "content-type" not in received.headers


@pytest.mark.parametrize(
    ("force_delete", "rewrite_mode"), [(False, False), (True, False), (False, True), (True, True)]
)
def test_a_crawl_sends_both_options_explicitly_and_unswapped(
    client: TestClient, server: LocalHttpServer, force_delete: bool, rewrite_mode: bool
) -> None:
    server.set_default_reply(
        json_reply(202, crawler_accepted_body(force_delete=force_delete, rewrite_mode=rewrite_mode))
    )

    response = client.post(
        f"{SOURCES}/docs/crawl-jobs",
        json={"force_delete": force_delete, "rewrite_mode": rewrite_mode},
    )

    assert response.status_code == 202
    [received] = server.requests
    assert received.request_line == "POST /sources/docs/crawl-jobs HTTP/1.1"
    assert json.loads(received.body) == {"force_delete": force_delete, "rewrite_mode": rewrite_mode}
    assert (response.json()["force_delete"], response.json()["rewrite_mode"]) == (
        force_delete,
        rewrite_mode,
    )


def test_a_crawl_without_a_body_sends_false_for_both_options(
    client: TestClient, server: LocalHttpServer
) -> None:
    server.set_default_reply(ACCEPTED_CRAWL)

    client.post(f"{SOURCES}/docs/crawl-jobs")

    [received] = server.requests
    assert json.loads(received.body) == {"force_delete": False, "rewrite_mode": False}


def test_a_lock_release_sends_one_delete(client: TestClient, server: LocalHttpServer) -> None:
    server.set_default_reply(RELEASED)

    response = client.delete(f"{SOURCES}/a.b/lock")

    assert response.status_code == 200
    [received] = server.requests
    assert received.request_line == "DELETE /sources/a%2Eb/lock HTTP/1.1"


@pytest.mark.parametrize(
    ("path_id", "expected_path"),
    [
        ("job-1", "job-1"),
        ("%2E", "%2E"),
        ("%2E%2E", "%2E%2E"),
        ("a%3Fb", "a%3Fb"),
        ("a%23b", "a%23b"),
        ("a%25b", "a%25b"),
        ("a%20b", "a%20b"),
        ("%E6%97%A5", "%E6%97%A5"),
    ],
    ids=["plain", "dot", "dotdot", "question", "hash", "percent", "space", "japanese"],
)
def test_a_cancel_sends_the_job_id_fully_encoded_so_it_stays_one_path_segment(
    client: TestClient, server: LocalHttpServer, path_id: str, expected_path: str
) -> None:
    server.set_default_reply(CANCELLED)

    response = client.post(f"{JOBS}/{path_id}/cancel")

    assert response.status_code == 200
    [received] = server.requests
    assert received.request_line == f"POST /jobs/{expected_path}/cancel HTTP/1.1"


def test_a_job_id_that_the_crawler_cannot_route_is_a_job_not_found(
    client: TestClient, server: LocalHttpServer
) -> None:
    """Crawler が `job_id` をパスとして扱えず返す 404 `not_found`・400 は、存在しない ID と同義。"""
    server.enqueue(
        error_reply(404, "not_found"),
        error_reply(400, "invalid_request", errors=[{"field": "job_id", "reason": "format"}]),
    )

    responses = [client.post(f"{JOBS}/x%3Fy/cancel"), client.post(f"{JOBS}/x%25y/cancel")]

    assert [r.status_code for r in responses] == [404, 404]
    assert [r.json()["error"]["code"] for r in responses] == ["job_not_found", "job_not_found"]


def test_the_same_responses_for_a_source_id_are_a_crawler_error(
    client: TestClient, server: LocalHttpServer
) -> None:
    server.enqueue(
        error_reply(404, "not_found"),
        error_reply(400, "invalid_request", errors=[{"field": "source_id", "reason": "format"}]),
    )

    responses = [client.delete(f"{SOURCES}/docs/lock"), client.post(f"{SOURCES}/docs/delete-jobs")]

    assert [r.status_code for r in responses] == [502, 502]
    assert [r.json()["error"]["code"] for r in responses] == ["crawler_error", "crawler_error"]


def test_a_request_that_fails_validation_never_reaches_the_crawler(
    client: TestClient, server: LocalHttpServer
) -> None:
    responses = [
        client.post(SOURCES, json=register_body(ratio_threshold_percent=100)),
        client.put(f"{SOURCES}/-bad", json=update_body()),
        client.post(f"{SOURCES}/docs/crawl-jobs", json={"force_delete": "yes"}),
        client.post(f"{JOBS}/a%2Fb/cancel"),
        client.delete(f"{SOURCES}/a b/lock"),
    ]

    assert [r.status_code for r in responses] == [400, 400, 400, 404, 400]
    assert server.requests == []


# --- 応答本文の上限: リクエスト本文の上限いっぱいの設定を保存した応答が、502 にならない ---

# Crawler は受け取った設定に `status`・`updated_at` などを足して返すので、応答の方が大きい。
RESPONSE_OVER_REQUEST_LIMIT_BYTES = 4 * 1024


def crawler_source_reply_of_size(status: int, num_bytes: int) -> StubReply:
    """本文がちょうど `num_bytes` の保存内容の応答(`connector_config` を水増しする)。"""
    empty = json.dumps(crawler_source_body(connector_config={"root": "/r", "pad": ""})).encode()
    pad = "x" * (num_bytes - len(empty))
    body = json.dumps(crawler_source_body(connector_config={"root": "/r", "pad": pad})).encode()
    assert len(body) == num_bytes
    return StubReply(status, body, JSON_HEADERS)


def test_a_registration_succeeds_when_the_response_is_larger_than_the_request_limit(
    client: TestClient, server: LocalHttpServer
) -> None:
    num_bytes = MAX_REQUEST_BODY_BYTES + RESPONSE_OVER_REQUEST_LIMIT_BYTES
    server.set_default_reply(crawler_source_reply_of_size(201, num_bytes))

    response = client.post(SOURCES, json=register_body())

    assert response.status_code == 201
    assert response.json()["source_id"] == "docs-share"


def test_an_update_succeeds_when_the_response_is_larger_than_the_request_limit(
    client: TestClient, server: LocalHttpServer
) -> None:
    num_bytes = MAX_REQUEST_BODY_BYTES + RESPONSE_OVER_REQUEST_LIMIT_BYTES
    server.set_default_reply(crawler_source_reply_of_size(200, num_bytes))

    response = client.put(f"{SOURCES}/docs-share", json=update_body())

    assert response.status_code == 200


def test_a_registration_response_over_the_limit_is_a_crawler_error(
    client: TestClient, server: LocalHttpServer
) -> None:
    server.set_default_reply(crawler_source_reply_of_size(201, RESPONSE_MAX_BYTES + 1))

    response = client.post(SOURCES, json=register_body())

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "crawler_error"


def test_an_update_response_over_the_limit_is_a_crawler_error(
    client: TestClient, server: LocalHttpServer
) -> None:
    server.set_default_reply(crawler_source_reply_of_size(200, RESPONSE_MAX_BYTES + 1))

    response = client.put(f"{SOURCES}/docs-share", json=update_body())

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "crawler_error"


# --- 409 の付随情報(実クライアントを通す) ---


def test_a_lock_conflict_over_http_keeps_the_existing_job_and_adds_the_lock_state(
    client: TestClient, server: LocalHttpServer, readers: InMemoryReaders
) -> None:
    existing_job = {
        "job_id": "job-20261122T010203Z-3fa9c2d1",
        "job_type": "crawl",
        "status": "running",
        "trigger": "schedule",
        "lease_expires_at": "2026-11-22T01:07:03.456Z",
    }
    seed_lock(readers, "lease_expired")
    server.set_default_reply(error_reply(409, "lock_held", existing_job=existing_job))

    response = client.post(
        f"{SOURCES}/docs/crawl-jobs", json={"force_delete": True, "rewrite_mode": False}
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "lock_held",
            "message": "the source is locked by another job",
            "retryable": False,
            "details": {
                "options_applied": False,
                "requested": {"force_delete": True, "rewrite_mode": False},
                "existing_job": existing_job,
                "lock_state": "lease_expired",
            },
        }
    }
    assert len(server.requests) == 1


# --- config_invalid の分解(実クライアントを通す) ---


@pytest.mark.parametrize(
    ("message", "expected_errors"),
    [
        (
            "root: `/` で始まる絶対パスでない",
            [
                {
                    "field": "connector_config.root",
                    "reason": "config_invalid",
                    "detail": "`/` で始まる絶対パスでない",
                }
            ],
        ),
        (
            "connector_config: オブジェクトでない",
            [
                {
                    "field": "connector_config",
                    "reason": "config_invalid",
                    "detail": "オブジェクトでない",
                }
            ],
        ),
        ("not a decomposable message", []),
    ],
)
def test_a_config_invalid_is_decomposed_through_the_real_client(
    client: TestClient,
    server: LocalHttpServer,
    message: str,
    expected_errors: list[dict[str, str]],
) -> None:
    server.set_default_reply(
        json_reply(
            400,
            {"error": {"code": "config_invalid", "message": message, "retryable": False}},
        )
    )

    response = client.post(SOURCES, json=register_body())

    assert response.status_code == 400
    assert response.json()["error"]["details"] == {
        "errors": expected_errors,
        "crawler_message": message,
    }


# --- 障害別(受信回数 1 回。C 11章 2) ---


@pytest.mark.parametrize(
    ("reply", "expected_status", "expected_code"),
    [
        (StubReply(503, b"<html>service unavailable</html>"), 502, "crawler_error"),
        (error_reply(503, "unavailable"), 503, "crawler_unavailable"),
        (error_reply(500, "internal_error"), 502, "crawler_error"),
        (StubReply(200, b"not json", JSON_HEADERS), 502, "crawler_error"),
        (StubReply(307, b"", {"Location": "/elsewhere"}), 502, "crawler_error"),
        (StubReply(200, b"{}", JSON_HEADERS), 502, "crawler_error"),  # EP-06 の成功は 202
        (StubReply(mode="drop"), 504, "crawler_response_lost"),
        (StubReply(202, b"{}", JSON_HEADERS, mode="truncate"), 504, "crawler_response_lost"),
    ],
    ids=[
        "503-not-json",
        "503",
        "500",
        "not-json",
        "redirect",
        "unexpected-2xx",
        "dropped",
        "truncated",
    ],
)
def test_a_failure_of_the_crawler_is_one_request_and_the_documented_error(
    client: TestClient,
    server: LocalHttpServer,
    reply: StubReply,
    expected_status: int,
    expected_code: str,
) -> None:
    server.set_default_reply(reply)

    response = client.post(f"{SOURCES}/docs/crawl-jobs", json={"force_delete": True})

    assert (response.status_code, response.json()["error"]["code"]) == (
        expected_status,
        expected_code,
    )
    assert len(server.requests) == 1  # 再送しない・リダイレクトを追わない
    assert server.connection_count == 1


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", SOURCES, register_body()),
        ("put", f"{SOURCES}/docs", update_body()),
        ("post", f"{SOURCES}/docs/delete-jobs", None),
        ("post", f"{SOURCES}/docs/crawl-jobs", {"force_delete": False}),
        ("post", f"{JOBS}/job-1/cancel", None),
        ("delete", f"{SOURCES}/docs/lock", None),
    ],
    ids=["EP-03", "EP-04", "EP-05", "EP-06", "EP-07", "EP-08"],
)
def test_a_lost_response_is_never_retried_for_any_endpoint(
    server: LocalHttpServer,
    readers: InMemoryReaders,
    method: str,
    path: str,
    body: Any,
) -> None:
    """応答がなくても再送しない(冪等でない起動系・DELETE・PUT を含む。受付済みかもしれない)。"""
    server.set_default_reply(StubReply(202, b"{}", JSON_HEADERS, delay_seconds=2.0))
    client, crawler = make_client(CrawlerClientConfig(server.url, 3.0, 0.2), readers)

    try:
        response = getattr(client, method)(path, **({"json": body} if body is not None else {}))
    finally:
        crawler.close()

    assert response.status_code == 504
    error = response.json()["error"]
    assert (error["code"], error["retryable"]) == ("crawler_response_lost", False)
    assert error["details"] == {"outcome_unknown": True}
    assert len(server.requests) == 1


def test_a_refused_connection_is_a_503_and_the_read_endpoints_still_work(
    readers: InMemoryReaders,
) -> None:
    config = CrawlerClientConfig(f"http://127.0.0.1:{closed_port()}", 1.0, 1.0)
    client, crawler = make_client(config, readers)
    readers.put_source("docs", connector_type="file_system", status="active")
    readers.refresh_search()

    try:
        write = client.post(f"{SOURCES}/docs/crawl-jobs")
        read = client.get(f"{SOURCES}/docs")
    finally:
        crawler.close()

    assert write.status_code == 503
    assert write.json()["error"] == {
        "code": "crawler_unreachable",
        "message": "the crawler is unreachable",
        "retryable": True,
    }
    assert read.status_code == 200


# --- 入力値・秘密を出さない(C 11章 12。実クライアントを DEBUG のログで通す) ---


class RecordsCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.mark.usefixtures("restore_logging")
def test_ids_connector_config_and_crawler_messages_are_in_neither_the_responses_nor_the_logs(
    client: TestClient, server: LocalHttpServer
) -> None:
    stream = io.StringIO()
    configure_logging(level="DEBUG", stream=stream)
    collector = RecordsCollector()
    logging.getLogger().addHandler(collector)
    rejection = json_reply(
        503, {"error": {"code": "unavailable", "message": SENTINEL, "retryable": True}}
    )
    server.set_default_reply(rejection)
    secret_id = f"id-{SENTINEL}"

    responses = [
        client.post(
            SOURCES, json=register_body(source_id=secret_id, connector_config={"root": SENTINEL})
        ),
        client.put(f"{SOURCES}/{secret_id}", json=update_body(connector_config={"root": SENTINEL})),
        client.post(f"{SOURCES}/{secret_id}/delete-jobs"),
        client.post(f"{SOURCES}/{secret_id}/crawl-jobs"),
        client.post(f"{JOBS}/{secret_id}/cancel"),
        client.delete(f"{SOURCES}/{secret_id}/lock"),
    ]

    assert [response.status_code for response in responses] == [503] * 6
    # テストのクライアント(httpx2)のログは、URL を出す。サーバー側の出力だけを対象にする。
    captured_text = "\n".join(
        line for line in stream.getvalue().splitlines() if " httpx2 " not in line
    )
    assert "crawler call: route=" in captured_text  # 呼び出しのログは出ている(捕捉できている)
    assert_secret_absent(
        SENTINEL,
        response_text="".join(response.text for response in responses),
        records=collector.records,
        captured_text=captured_text,
    )
