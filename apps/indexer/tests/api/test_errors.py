"""例外から HTTP 応答への写像と、共通のエラー形式(api 3.4、plan 案 15)。"""

import asyncio
import logging
import re
import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from loreley_indexer.api import create_api_app
from loreley_indexer.api.errors import InvalidRequestError, describe_origin
from loreley_indexer.api.request_body import read_limited_body
from loreley_indexer.common.errors import ContractError, IndexerError, UnavailableError
from loreley_indexer.crawl_runs.lifecycle import MalformedRecordError
from loreley_indexer.infrastructure.opensearch import (
    OpenSearchUnavailableError,
    OpenSearchUnexpectedResponseError,
)
from tests.api.factories import STATUS_PATH, start_json
from tests.api.stubs import StubDependencies, make_api_config, make_stub_app, stub_client

SENTINEL = "SENTINEL-IN-EXCEPTION-MESSAGE"


def all_contract_errors() -> list[type[ContractError]]:
    found: list[type[ContractError]] = []
    pending = [ContractError]
    while pending:
        for subclass in pending.pop().__subclasses__():
            pending.append(subclass)
            if hasattr(subclass, "code"):
                found.append(subclass)
    return found


# --- 契約のエラー(ContractError)は、クラスの値をそのまま返す ---


def test_every_contract_error_is_listed_so_that_a_new_one_is_not_forgotten() -> None:
    assert {error.code for error in all_contract_errors()} == {
        "crawl_not_started",
        "crawl_source_mismatch",
        "crawl_started_at_mismatch",
        "crawl_already_closed",
        "crawl_finished",
        "crawl_already_finished",
        "crawl_start_conflict",
        "stale_crawl_started_at",
        "finish_source_mismatch",
        "finish_content_mismatch",
        "crawl_not_found",
        "lock_not_owned",
    }


@pytest.mark.parametrize("error_class", all_contract_errors(), ids=lambda c: c.__name__)
def test_a_contract_error_is_returned_with_its_status_code_message_and_retryable(
    error_class: type[ContractError],
) -> None:
    stubs = StubDependencies()
    stubs.crawl_runs.crawl_status.side_effect = error_class()

    with stub_client(stubs) as client:
        response = client.get(STATUS_PATH)

    assert response.status_code == error_class.status_code
    assert response.json() == {
        "error": {
            "code": error_class.code,
            "message": error_class.message,
            "retryable": error_class.retryable,
        }
    }
    assert response.headers["content-type"] == "application/json"


# --- 503 ---


def test_the_opensearch_errors_that_api_maps_are_subclasses_of_the_common_ones() -> None:
    """api は infrastructure を import できないので、`common` の基底クラスで写像している。"""
    assert issubclass(OpenSearchUnavailableError, UnavailableError)
    assert issubclass(OpenSearchUnexpectedResponseError, IndexerError)
    assert issubclass(MalformedRecordError, IndexerError)
    assert not issubclass(OpenSearchUnexpectedResponseError, UnavailableError)
    assert not issubclass(MalformedRecordError, ContractError)


@pytest.mark.parametrize(
    "error",
    [
        UnavailableError("write_conflict"),
        OpenSearchUnavailableError("http_503"),
        UnavailableError(SENTINEL),
    ],
    ids=["common", "opensearch", "reason-with-a-value"],
)
def test_an_unavailable_error_is_a_503_that_is_retryable_with_a_fixed_message(
    error: UnavailableError,
) -> None:
    stubs = StubDependencies()
    stubs.crawl_runs.crawl_status.side_effect = error

    with stub_client(stubs) as client:
        response = client.get(STATUS_PATH)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "unavailable",
            "message": "the service is temporarily unavailable",
            "retryable": True,
        }
    }


# --- 500 ---


@pytest.mark.parametrize(
    "error",
    [
        MalformedRecordError("ttl"),
        OpenSearchUnexpectedResponseError(SENTINEL),
        IndexerError(SENTINEL),
        RuntimeError(SENTINEL),
        KeyError(SENTINEL),
        ZeroDivisionError(SENTINEL),
        AssertionError(SENTINEL),
        RecursionError(SENTINEL),
    ],
    ids=lambda error: type(error).__name__,
)
def test_an_unexpected_error_is_a_500_with_a_fixed_message_and_is_not_reraised(
    error: Exception,
) -> None:
    stubs = StubDependencies()
    stubs.crawl_runs.crawl_status.side_effect = error

    # 例外を再送出しない(サーバのスタックトレースのログに、入力値が出ない)ことを、
    # 例外を再送出する設定のクライアントで確かめる。
    with stub_client(stubs, raise_server_exceptions=True) as client:
        response = client.get(STATUS_PATH)

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "an internal error occurred",
            "retryable": False,
        }
    }
    assert SENTINEL not in response.text


@pytest.mark.parametrize("message", ["ttl must be an integer", SENTINEL])
def test_a_value_error_from_the_domain_is_a_400_with_a_fixed_message(message: str) -> None:
    stubs = StubDependencies()
    stubs.crawl_runs.start_crawl.side_effect = ValueError(message)

    with stub_client(stubs) as client:
        response = client.post("/crawls/start", json=start_json())

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "invalid_request",
            "message": "the request is invalid",
            "retryable": False,
        }
    }


def test_a_unicode_error_is_a_400_not_a_500() -> None:
    """孤立サロゲートの送信で起きうる(`UnicodeEncodeError` は ValueError の一種)。"""
    stubs = StubDependencies()
    stubs.crawl_runs.start_crawl.side_effect = UnicodeEncodeError(
        "utf-8", "\ud800", 0, 1, "surrogates not allowed"
    )

    with stub_client(stubs) as client:
        response = client.post("/crawls/start", json=start_json())

    assert response.status_code == 400


# --- ルートにない・メソッドが違う ---


@pytest.mark.parametrize(
    ("method", "path", "status_code", "code"),
    [
        ("GET", "/unknown", 404, "not_found"),
        ("GET", "/sources/s1/last-seen", 405, "method_not_allowed"),
        ("PUT", "/crawls/start", 405, "method_not_allowed"),
        ("GET", "/docs", 404, "not_found"),
        ("GET", "/openapi.json", 404, "not_found"),
    ],
)
def test_an_unknown_route_or_method_uses_the_common_error_format(
    method: str, path: str, status_code: int, code: str
) -> None:
    with stub_client() as client:
        response = client.request(method, path)

    assert response.status_code == status_code
    error = response.json()["error"]
    assert (error["code"], error["retryable"]) == (code, False)
    assert path not in error["message"]


# --- 起動前(ready でない間)は、どのパスも 503 ---


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/healthz"), ("POST", "/crawls/start"), ("GET", STATUS_PATH), ("GET", "/unknown")],
)
def test_every_request_is_a_503_until_the_application_is_ready(method: str, path: str) -> None:
    stubs = StubDependencies()
    app = make_stub_app(stubs, ready=False)

    # `with` を使わないので lifespan は動かない(起動前の状態)。
    response = TestClient(app).request(
        method, path, json=start_json() if method == "POST" else None
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unavailable"
    assert response.json()["error"]["retryable"] is True
    assert stubs.calls() == []


def test_requests_are_accepted_once_the_ready_event_is_set() -> None:
    ready = threading.Event()
    stubs = StubDependencies()
    app = create_api_app(
        dependencies=stubs.as_dependencies(), config=make_api_config(), ready=ready
    )
    client = TestClient(app)

    assert client.get("/healthz").status_code == 503
    ready.set()
    assert client.get("/healthz").status_code == 200
    ready.clear()
    assert client.get("/healthz").status_code == 503


def test_the_error_body_never_has_extra_keys() -> None:
    with stub_client() as client:
        bodies: list[Any] = [
            client.get("/unknown").json(),
            client.post("/crawls/start", content=b"x").json(),
        ]

    assert all(set(body) == {"error"} for body in bodies)
    assert all(set(body["error"]) == {"code", "message", "retryable"} for body in bodies)


# --- ログ: 値を含まない診断情報だけを出す(R9) ---


def raise_a_value_error_with_a_value(*_arguments: object) -> None:
    value_in_a_local_variable = SENTINEL
    raise ValueError(value_in_a_local_variable)


def raise_a_runtime_error_with_a_value(*_arguments: object) -> None:
    value_in_a_local_variable = SENTINEL
    raise RuntimeError(value_in_a_local_variable)


def logs_of(caplog: pytest.LogCaptureFixture, level: int) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == "loreley_indexer.api.errors" and record.levelno == level
    ]


def test_a_value_error_is_logged_with_its_class_and_origin_but_never_its_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ドメインの形式不正でない `ValueError`(バグ・ライブラリ)も 400 になる。手がかりを残す。"""
    caplog.set_level(logging.DEBUG)
    stubs = StubDependencies()
    stubs.crawl_runs.start_crawl.side_effect = raise_a_value_error_with_a_value

    with stub_client(stubs) as client:
        response = client.post("/crawls/start", json=start_json(crawl_id=SENTINEL))

    assert response.status_code == 400
    [warning] = logs_of(caplog, logging.WARNING)
    assert re.fullmatch(
        r"domain rejected the request: error=ValueError "
        r"origin=api/test_errors\.py:\d+ raise_a_value_error_with_a_value",
        warning.getMessage(),
    )
    assert warning.exc_info is None
    assert SENTINEL not in caplog.text  # 例外のメッセージ・ローカル変数・リクエストの値


def test_a_unicode_error_is_logged_by_its_class_without_the_offending_characters(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    stubs = StubDependencies()
    stubs.crawl_runs.start_crawl.side_effect = UnicodeEncodeError(
        "utf-8", "SENTINEL\ud800", 8, 9, "surrogates not allowed"
    )

    with stub_client(stubs) as client:
        client.post("/crawls/start", json=start_json())

    [warning] = logs_of(caplog, logging.WARNING)
    assert warning.getMessage().startswith("domain rejected the request: error=UnicodeEncodeError ")
    assert "SENTINEL" not in caplog.text


def test_an_unexpected_error_is_logged_with_its_class_and_origin_but_never_its_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    stubs = StubDependencies()
    stubs.crawl_runs.crawl_status.side_effect = raise_a_runtime_error_with_a_value

    with stub_client(stubs) as client:
        client.get(STATUS_PATH)

    [error] = logs_of(caplog, logging.ERROR)
    assert re.fullmatch(
        r"request failed unexpectedly: error=RuntimeError "
        r"origin=api/test_errors\.py:\d+ raise_a_runtime_error_with_a_value",
        error.getMessage(),
    )
    assert SENTINEL not in caplog.text


@pytest.mark.parametrize("error_type", ["parsing_exception", "mapper_parsing_exception"])
def test_an_unexpected_response_is_logged_with_its_error_type(
    caplog: pytest.LogCaptureFixture, error_type: str
) -> None:
    """検索基盤の想定外の応答は、種別名(値を含まない)が診断の手がかりになる。"""
    caplog.set_level(logging.DEBUG)
    stubs = StubDependencies()
    stubs.crawl_runs.crawl_status.side_effect = OpenSearchUnexpectedResponseError(error_type)

    with stub_client(stubs) as client:
        response = client.get(STATUS_PATH)

    assert response.status_code == 500
    [error] = logs_of(caplog, logging.ERROR)
    expected_prefix = (
        "request failed unexpectedly: error=OpenSearchUnexpectedResponseError "
        f"error_type={error_type} origin="
    )
    assert error.getMessage().startswith(expected_prefix)


def test_an_error_without_a_traceback_has_an_unknown_origin() -> None:
    assert describe_origin(ValueError("x")) == "unknown"


def test_the_origin_is_the_innermost_frame_of_the_traceback() -> None:
    def inner() -> None:
        raise ValueError("x")

    def outer() -> None:
        inner()

    with pytest.raises(ValueError) as excinfo:
        outer()

    origin = describe_origin(excinfo.value)
    assert re.fullmatch(r"api/test_errors\.py:\d+ inner", origin)


# --- リクエストボディの読み込み中の切断 ---


def test_a_disconnect_while_reading_the_body_is_a_400_not_an_internal_error() -> None:
    async def receive() -> dict[str, Any]:
        return {"type": "http.disconnect"}

    request = Request({"type": "http", "method": "POST", "headers": []}, receive)

    with pytest.raises(InvalidRequestError, match="not fully received"):
        asyncio.run(read_limited_body(request, max_bytes=100))


def test_a_client_that_disconnects_mid_body_does_not_log_an_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    stubs = StubDependencies()
    app = make_stub_app(stubs)
    messages = iter(
        [
            {"type": "http.request", "body": b'{"crawl_id": ', "more_body": True},
            {"type": "http.disconnect"},
        ]
    )
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return next(messages, {"type": "http.disconnect"})

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/crawls/start",
        "raw_path": b"/crawls/start",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
    }

    asyncio.run(app(scope, receive, send))

    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []
    assert stubs.calls() == []
