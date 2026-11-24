"""実際の HTTP クライアント(`HttpCrawlerClient`)とローカル HTTP スタブを通した写像(C 11章 1〜4)。

クライアントの解釈(`CrawlerRejected` など)と写像(`translate`)をつなげて、Crawler が返す形のとおりの
応答が、B 9.2 の表どおりの Admin API のエラーになることを確かめる。表の全行は `test_translate.py`。
"""

import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from loreley_api.admin.base.errors import AdminApiError
from loreley_api.admin.crawler_mapping import CrawlerOperation, RequestedOptions, translate
from loreley_api.infrastructure.crawler_client import (
    CrawlerClientConfig,
    CrawlerResult,
    CrawlerSourceSettings,
    HttpCrawlerClient,
)
from tests.fakes.local_http_server import (
    LocalHttpServer,
    StubReply,
    closed_port,
    local_http_server,
)

SETTINGS = CrawlerSourceSettings(
    connector_config={"root": "/data"},
    ttl_seconds=86_400,
    ratio_threshold=0.2,
    min_delete_count=1,
    schedule_cron=None,
)
JSON_HEADERS = {"Content-Type": "application/json"}

Call = Callable[[HttpCrawlerClient], CrawlerResult]
CANCEL_JOB: Call = lambda client: client.cancel_job("job-1")  # noqa: E731
RELEASE_LOCK: Call = lambda client: client.release_lock("docs")  # noqa: E731
START_CRAWL: Call = lambda client: client.start_crawl(  # noqa: E731
    "docs", force_delete=False, rewrite_mode=False
)
REGISTER: Call = lambda client: client.register_source("docs", "file_system", SETTINGS)  # noqa: E731


def error_reply(status: int, code: str, message: str = "fixed", **details: object) -> StubReply:
    error: dict[str, Any] = {"code": code, "message": message, "retryable": False}
    if details:
        error["details"] = details
    return StubReply(status, json.dumps({"error": error}).encode(), JSON_HEADERS)


@pytest.fixture
def server() -> Iterator[LocalHttpServer]:
    with local_http_server() as stub:
        yield stub


def run(
    server: LocalHttpServer,
    operation: CrawlerOperation,
    call: Call,
    reply: StubReply,
    *,
    requested: RequestedOptions | None = None,
) -> AdminApiError:
    server.set_default_reply(reply)
    client = HttpCrawlerClient(CrawlerClientConfig(server.url, 3.0, 5.0))
    try:
        translated = translate(operation, call(client), requested=requested)
    finally:
        client.close()
    assert isinstance(translated, AdminApiError)
    return translated


def test_a_cancel_rejected_for_the_job_id_by_the_crawler_is_a_job_not_found(
    server: LocalHttpServer,
) -> None:
    """Crawler が `job_id` の形で返す 400(項目 `job_id`)。"""
    reply = error_reply(400, "invalid_request", errors=[{"field": "job_id", "reason": "format"}])

    error = run(server, CrawlerOperation.CANCEL_JOB, CANCEL_JOB, reply)

    assert (error.status_code, error.code) == (404, "job_not_found")


def test_a_cancel_that_the_crawler_could_not_route_is_a_job_not_found(
    server: LocalHttpServer,
) -> None:
    """`/` を含む `job_id` は、Crawler がパスとして扱えず 404 `not_found` を返す。"""
    error = run(server, CrawlerOperation.CANCEL_JOB, CANCEL_JOB, error_reply(404, "not_found"))

    assert (error.status_code, error.code) == (404, "job_not_found")


def test_the_same_responses_of_an_api_with_a_source_id_are_a_crawler_error(
    server: LocalHttpServer,
) -> None:
    for reply in (
        error_reply(404, "not_found"),
        error_reply(400, "invalid_request", errors=[{"field": "source_id", "reason": "format"}]),
    ):
        error = run(server, CrawlerOperation.RELEASE_LOCK, RELEASE_LOCK, reply)

        assert (error.status_code, error.code) == (502, "crawler_error")


def test_a_lock_conflict_keeps_the_existing_job_of_the_crawler_response(
    server: LocalHttpServer,
) -> None:
    existing_job = {
        "job_id": "job-1",
        "job_type": "crawl",
        "status": "running",
        "trigger": "manual",
        "lease_expires_at": "2026-11-22T01:07:03.456Z",
    }
    reply = error_reply(409, "lock_held", existing_job=existing_job)

    error = run(
        server,
        CrawlerOperation.START_CRAWL,
        START_CRAWL,
        reply,
        requested=RequestedOptions(force_delete=False, rewrite_mode=False),
    )

    assert error.details is not None
    assert error.details["existing_job"] == existing_job


def test_a_config_invalid_of_the_crawler_is_decomposed_by_the_client_and_mapped(
    server: LocalHttpServer,
) -> None:
    message = "include_patterns[2]: `\\` を含む(エスケープはない)"

    error = run(
        server,
        CrawlerOperation.REGISTER_SOURCE,
        REGISTER,
        error_reply(400, "config_invalid", message),
    )

    assert (error.status_code, error.code) == (400, "config_invalid")
    assert error.details == {
        "errors": [
            {
                "field": "connector_config.include_patterns[2]",
                "reason": "config_invalid",
                "detail": "`\\` を含む(エスケープはない)",
            }
        ],
        "crawler_message": message,
    }


@pytest.mark.parametrize(
    "reply",
    [
        StubReply(307, b"", {"Location": "/elsewhere"}),
        StubReply(502, b"<html>bad gateway</html>"),
        StubReply(200, b"{}", JSON_HEADERS),  # 登録の成功は 201(または冪等の 200)。取消は 200・202
        StubReply(500, b"not json"),
        error_reply(500, "internal_error"),
        error_reply(404, "not_found"),
        error_reply(405, "method_not_allowed"),
        error_reply(400, "http_error"),
        error_reply(418, "something_new"),
    ],
    ids=[
        "redirect",
        "html",
        "ok-json-wrong-status",
        "500-not-json",
        "500",
        "404",
        "405",
        "http",
        "new",
    ],
)
def test_an_unexpected_response_of_start_crawl_is_a_crawler_error(
    server: LocalHttpServer, reply: StubReply
) -> None:
    error = run(server, CrawlerOperation.START_CRAWL, START_CRAWL, reply)

    assert (error.status_code, error.code, error.retryable) == (502, "crawler_error", False)


def test_a_refused_connection_is_crawler_unreachable() -> None:
    client = HttpCrawlerClient(CrawlerClientConfig(f"http://127.0.0.1:{closed_port()}", 3.0, 5.0))

    translated = translate(CrawlerOperation.START_CRAWL, START_CRAWL(client))

    assert isinstance(translated, AdminApiError)
    assert (translated.status_code, translated.code, translated.retryable) == (
        503,
        "crawler_unreachable",
        True,
    )


def test_a_response_timeout_is_crawler_response_lost_and_the_request_was_sent_once(
    server: LocalHttpServer,
) -> None:
    server.set_default_reply(StubReply(202, b"{}", JSON_HEADERS, delay_seconds=2.0))
    client = HttpCrawlerClient(CrawlerClientConfig(server.url, 3.0, 0.2))

    translated = translate(CrawlerOperation.START_CRAWL, START_CRAWL(client))

    assert isinstance(translated, AdminApiError)
    assert (translated.status_code, translated.code) == (504, "crawler_response_lost")
    assert translated.details == {"outcome_unknown": True}
    assert len(server.requests) == 1
