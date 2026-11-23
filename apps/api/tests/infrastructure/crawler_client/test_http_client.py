"""`HttpCrawlerClient` を、ローカル HTTP スタブで確かめる(C 4.1〜4.3・4.8。C 11章 1〜3)。

実 HTTP のため、受けた**生のリクエスト行**・回数・接続の数・ヘッダ・本文を確かめられる。
接続拒否は閉じたポート、名前解決の失敗は `.invalid` のホストで再現する(実 DNS に問い合わせるのは、
名前解決の分類を確かめる 1 件だけ。ほかのテストは `unresolvable_invalid_hosts` を使う)。
"""

import json
from collections.abc import Callable, Iterator
from typing import Any, NoReturn

import pytest
from urllib3.connection import HTTPConnection
from urllib3.exceptions import NewConnectionError

from loreley_api.infrastructure.crawler_client import (
    CrawlerClientConfig,
    CrawlerContractViolation,
    CrawlerRejected,
    CrawlerResult,
    CrawlerSourceSettings,
    CrawlerSucceeded,
    CrawlerTransportFailed,
    HttpCrawlerClient,
)
from loreley_api.infrastructure.crawler_client.parsing import RESPONSE_MAX_BYTES
from tests.fakes.local_http_server import (
    LocalHttpServer,
    StubReply,
    closed_port,
    local_http_server,
)

SETTINGS = CrawlerSourceSettings(
    connector_config={"root": "/data/documents"},
    ttl_seconds=86_400,
    ratio_threshold=0.2,
    min_delete_count=10,
    schedule_cron=None,
)
JSON_HEADERS = {"Content-Type": "application/json"}


def json_reply(status: int, payload: object, **kwargs: Any) -> StubReply:
    return StubReply(status, json.dumps(payload).encode(), JSON_HEADERS, **kwargs)


def error_reply(status: int, code: str, **details: object) -> StubReply:
    error: dict[str, object] = {"code": code, "message": "fixed", "retryable": False}
    if details:
        error["details"] = details
    return json_reply(status, {"error": error})


@pytest.fixture
def server() -> Iterator[LocalHttpServer]:
    with local_http_server() as stub:
        yield stub


def make_client(
    base_url: str, *, response_timeout_seconds: float = 5.0, connect_timeout_seconds: float = 3.0
) -> HttpCrawlerClient:
    return HttpCrawlerClient(
        CrawlerClientConfig(base_url, connect_timeout_seconds, response_timeout_seconds)
    )


# --- 6 操作: メソッド・パス・本文・ヘッダ・成功の解釈 ---

Call = Callable[[HttpCrawlerClient], CrawlerResult]

OPERATION_CASES: list[tuple[str, Call, str, str, dict[str, Any] | None, StubReply]] = [
    (
        "register_source",
        lambda client: client.register_source("docs.v2", "file_system", SETTINGS),
        "POST",
        "/sources",
        {
            "source_id": "docs.v2",
            "connector_type": "file_system",
            "connector_config": {"root": "/data/documents"},
            "ttl": 86_400,
            "ratio_threshold": 0.2,
            "min_delete_count": 10,
            "schedule_cron": None,
        },
        json_reply(201, {"source_id": "docs.v2"}),
    ),
    (
        "update_source",
        lambda client: client.update_source("docs.v2", SETTINGS),
        "PUT",
        "/sources/docs%2Ev2",
        {
            "connector_config": {"root": "/data/documents"},
            "ttl": 86_400,
            "ratio_threshold": 0.2,
            "min_delete_count": 10,
            "schedule_cron": None,
        },
        json_reply(200, {"source_id": "docs.v2"}),
    ),
    (
        "start_delete_job",
        lambda client: client.start_delete_job("docs.v2"),
        "POST",
        "/sources/docs%2Ev2/delete-jobs",
        None,
        json_reply(202, {"job_id": "j"}),
    ),
    (
        "start_crawl",
        lambda client: client.start_crawl("docs.v2", force_delete=True, rewrite_mode=False),
        "POST",
        "/sources/docs%2Ev2/crawl-jobs",
        {"force_delete": True, "rewrite_mode": False},
        json_reply(202, {"job_id": "j"}),
    ),
    (
        "cancel_job",
        lambda client: client.cancel_job("job-1"),
        "POST",
        "/jobs/job-1/cancel",
        None,
        json_reply(202, {"job_id": "job-1", "status": "running"}),
    ),
    (
        "release_lock",
        lambda client: client.release_lock("docs.v2"),
        "DELETE",
        "/sources/docs%2Ev2/lock",
        None,
        json_reply(200, {"source_id": "docs.v2", "released": True, "failed_job_id": None}),
    ),
]


@pytest.mark.parametrize(
    ("name", "call", "method", "path", "payload", "reply"),
    OPERATION_CASES,
    ids=[case[0] for case in OPERATION_CASES],
)
def test_each_operation_sends_one_fixed_request_and_returns_the_parsed_success(
    server: LocalHttpServer,
    name: str,
    call: Call,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    reply: StubReply,
) -> None:
    server.enqueue(reply)
    client = make_client(server.url)

    result = call(client)

    [request] = server.requests
    assert request.request_line == f"{method} {path} HTTP/1.1"
    assert isinstance(result, CrawlerSucceeded)
    assert result.status == reply.status
    assert request.headers["connection"] == "close"
    assert request.headers["accept"] == "application/json"
    if payload is None:
        assert request.body == b""  # 本文を読まない API には本文を付けない
        assert "content-type" not in request.headers
    else:
        assert json.loads(request.body) == payload
        assert request.headers["content-type"] == "application/json"


def test_a_200_body_of_cancel_is_also_accepted() -> None:
    with local_http_server() as server:
        server.enqueue(json_reply(200, {"job_id": "j", "status": "cancelled"}))

        result = make_client(server.url).cancel_job("j")

    assert result == CrawlerSucceeded(200, {"job_id": "j", "status": "cancelled"})


def test_register_accepts_200_for_an_idempotent_repeat() -> None:
    with local_http_server() as server:
        server.enqueue(json_reply(200, {"source_id": "s"}))

        result = make_client(server.url).register_source("s", "file_system", SETTINGS)

    assert result == CrawlerSucceeded(200, {"source_id": "s"})


# --- パスのエンコード(生のリクエスト行。C 11章 3) ---


@pytest.mark.parametrize(
    ("job_id", "encoded"),
    [
        (".", "%2E"),
        ("..", "%2E%2E"),
        ("a%2Fb", "a%252Fb"),
        ("%", "%25"),
        ("x?y#z", "x%3Fy%23z"),
        ("a/b", "a%2Fb"),
        ("a b", "a%20b"),
        ("job-20261122T010203Z-3fa9c2d1", "job-20261122T010203Z-3fa9c2d1"),
        ("日本", "%E6%97%A5%E6%9C%AC"),
    ],
)
def test_a_job_id_reaches_the_server_encoded_in_every_character(
    server: LocalHttpServer, job_id: str, encoded: str
) -> None:
    server.set_default_reply(json_reply(200, {"job_id": job_id, "status": "cancelled"}))

    make_client(server.url).cancel_job(job_id)

    [request] = server.requests
    # ドットセグメントとして除去されず、`/jobs/{id}/cancel` のままの経路で届く。
    assert request.request_line == f"POST /jobs/{encoded}/cancel HTTP/1.1"


@pytest.mark.parametrize("source_id", ["a.b", "docs", "A1._-x"])
def test_a_source_id_with_a_dot_is_sent_with_the_dot_encoded(
    server: LocalHttpServer, source_id: str
) -> None:
    server.set_default_reply(json_reply(200, {}))
    client = make_client(server.url)

    client.release_lock(source_id)
    client.update_source(source_id, SETTINGS)

    expected = source_id.replace(".", "%2E")
    lines = [request.request_line for request in server.requests]
    assert lines == [
        f"DELETE /sources/{expected}/lock HTTP/1.1",
        f"PUT /sources/{expected} HTTP/1.1",
    ]


def test_the_trailing_slash_of_the_base_url_does_not_double_the_separator(
    server: LocalHttpServer,
) -> None:
    server.set_default_reply(json_reply(200, {}))

    make_client(f"{server.url}/").release_lock("docs")

    assert server.requests[0].request_line == "DELETE /sources/docs/lock HTTP/1.1"


# --- 再送しない・接続を使い回さない・リダイレクトに従わない ---


def test_every_request_uses_a_new_connection(server: LocalHttpServer) -> None:
    server.set_default_reply(json_reply(200, {}))
    client = make_client(server.url)

    for _ in range(3):
        client.release_lock("docs")

    assert len(server.requests) == 3
    assert server.connection_count == 3


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (error_reply(503, "unavailable"), CrawlerRejected(503, "unavailable", None, None)),
        (error_reply(500, "internal_error"), CrawlerRejected(500, "internal_error", None, None)),
        (
            StubReply(502, b"<html>bad gateway</html>"),
            CrawlerContractViolation("malformed_error", 502),
        ),
        (StubReply(202, b"not json"), CrawlerContractViolation("malformed_body", 202)),
    ],
    ids=["503", "500", "html-502", "non-json-200"],
)
def test_an_error_response_is_not_retried(
    server: LocalHttpServer, reply: StubReply, expected: CrawlerResult
) -> None:
    server.set_default_reply(reply)

    result = make_client(server.url).start_crawl("docs", force_delete=False, rewrite_mode=False)

    assert result == expected
    assert len(server.requests) == 1


def test_a_redirect_is_not_followed_and_is_a_contract_violation(server: LocalHttpServer) -> None:
    server.set_default_reply(StubReply(307, b"", {"Location": f"{server.url}/elsewhere"}))

    result = make_client(server.url).release_lock("docs")

    assert result == CrawlerContractViolation("redirect", 307)
    assert [request.request_line for request in server.requests] == [
        "DELETE /sources/docs/lock HTTP/1.1"
    ]  # Location の先へは行かない


def test_a_response_timeout_is_after_send_and_is_not_retried(server: LocalHttpServer) -> None:
    server.set_default_reply(json_reply(202, {}, delay_seconds=2.0))
    client = make_client(server.url, response_timeout_seconds=0.2)

    result = client.start_crawl("docs", force_delete=False, rewrite_mode=False)

    assert result == CrawlerTransportFailed("after_send", "response_timeout")
    assert len(server.requests) == 1  # 送った要求は 1 回だけ(再送で二重に起動しない)


def test_a_dropped_connection_is_after_send_and_is_not_retried(server: LocalHttpServer) -> None:
    server.set_default_reply(StubReply(mode="drop"))

    result = make_client(server.url).start_delete_job("docs")

    assert result == CrawlerTransportFailed("after_send", "connection_lost")
    assert len(server.requests) == 1


def test_a_truncated_body_is_after_send(server: LocalHttpServer) -> None:
    server.set_default_reply(StubReply(202, b'{"job_id": "j"', JSON_HEADERS, mode="truncate"))

    result = make_client(server.url).start_delete_job("docs")

    assert result == CrawlerTransportFailed("after_send", "connection_lost")
    assert len(server.requests) == 1


@pytest.mark.parametrize(
    ("name", "call"),
    [
        ("release_lock", lambda client: client.release_lock("docs")),
        ("update_source", lambda client: client.update_source("docs", SETTINGS)),
    ],
)
def test_an_idempotent_method_is_not_retried_either(
    server: LocalHttpServer, name: str, call: Call
) -> None:
    """urllib3 は、冪等なメソッド(DELETE・PUT)の読み取りの失敗を、既定では再送する。"""
    server.set_default_reply(StubReply(mode="drop"))

    result = call(make_client(server.url))

    assert result == CrawlerTransportFailed("after_send", "connection_lost"), name
    assert len(server.requests) == 1


def test_a_failed_connection_attempt_is_made_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """接続の確立の失敗も再送しない(`retries=False`)。確立の試みの回数を数える。"""
    attempts: list[str] = []

    def refuse(self: HTTPConnection) -> NoReturn:
        attempts.append(self.host)
        raise NewConnectionError(self, "refused")

    monkeypatch.setattr(HTTPConnection, "_new_conn", refuse)

    result = make_client("http://127.0.0.1:9").release_lock("docs")

    assert result == CrawlerTransportFailed("before_send", "connection_failed")
    assert len(attempts) == 1


def test_a_refused_connection_is_before_send() -> None:
    client = make_client(f"http://127.0.0.1:{closed_port()}")

    result = client.release_lock("docs")

    assert result == CrawlerTransportFailed("before_send", "connection_failed")


def test_an_unresolvable_host_is_before_send() -> None:
    # 実 DNS に問い合わせる唯一のテスト。DNS が応答しない環境では、失敗するまで遅くなりうる。
    client = make_client("http://crawler.invalid:8001")

    result = client.release_lock("docs")

    assert result == CrawlerTransportFailed("before_send", "name_resolution")


# --- 応答の解釈(契約外) ---


def test_an_unexpected_2xx_status_is_a_contract_violation(server: LocalHttpServer) -> None:
    server.set_default_reply(json_reply(200, {"job_id": "j"}))  # 削除ジョブ起動の成功は 202

    result = make_client(server.url).start_delete_job("docs")

    assert result == CrawlerContractViolation("unexpected_status", 200)


def test_a_body_of_exactly_one_mebibyte_is_accepted(server: LocalHttpServer) -> None:
    overhead = len(json.dumps({"pad": ""}))
    body = json.dumps({"pad": "x" * (RESPONSE_MAX_BYTES - overhead)}).encode()
    assert len(body) == RESPONSE_MAX_BYTES
    server.set_default_reply(StubReply(200, body, JSON_HEADERS))

    result = make_client(server.url).release_lock("docs")

    assert isinstance(result, CrawlerSucceeded)


def test_a_body_over_one_mebibyte_is_a_contract_violation(server: LocalHttpServer) -> None:
    server.set_default_reply(StubReply(200, b" " * (RESPONSE_MAX_BYTES + 1), JSON_HEADERS))

    result = make_client(server.url).release_lock("docs")

    assert result == CrawlerContractViolation("body_too_large", 200)
    assert len(server.requests) == 1


def test_a_config_invalid_response_is_decomposed(server: LocalHttpServer) -> None:
    server.set_default_reply(
        json_reply(
            400,
            {"error": {"code": "config_invalid", "message": "root: `/` で始まる絶対パスでない"}},
        )
    )

    result = make_client(server.url).register_source("docs", "file_system", SETTINGS)

    assert isinstance(result, CrawlerRejected)
    assert result.config_invalid is not None
    assert result.config_invalid.violation is not None
    assert result.config_invalid.violation.field == "connector_config.root"


def test_a_lock_conflict_keeps_the_existing_job_details(server: LocalHttpServer) -> None:
    existing = {"job_id": "j", "job_type": "crawl", "status": "running"}
    server.set_default_reply(error_reply(409, "lock_held", existing_job=existing))

    result = make_client(server.url).start_crawl("docs", force_delete=False, rewrite_mode=False)

    assert result == CrawlerRejected(409, "lock_held", {"existing_job": existing}, None)


def test_close_can_be_called_and_the_client_stays_usable(server: LocalHttpServer) -> None:
    server.set_default_reply(json_reply(200, {}))
    client = make_client(server.url)
    client.release_lock("docs")

    client.close()

    assert isinstance(client.release_lock("docs"), CrawlerSucceeded)
