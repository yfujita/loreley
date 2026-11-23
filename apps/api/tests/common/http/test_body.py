"""本文の上限(A 5.1。1 MiB)。超過は 400 `invalid_request`(`details` なし)。"""

from collections.abc import Iterator

import anyio
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from loreley_api.common.http import install_common_http
from loreley_api.common.http.body import MAX_REQUEST_BODY_BYTES, read_limited_body

SMALL_LIMIT = 10


@pytest.fixture
def client() -> TestClient:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)

    @app.post("/default")
    async def read_default(request: Request) -> dict[str, int]:
        return {"length": len(await read_limited_body(request))}

    @app.post("/small")
    async def read_small(request: Request) -> dict[str, int]:
        return {"length": len(await read_limited_body(request, max_bytes=SMALL_LIMIT))}

    install_common_http(app)
    return TestClient(app)


def test_the_limit_is_1_mib() -> None:
    assert MAX_REQUEST_BODY_BYTES == 1024 * 1024


def test_a_body_at_the_limit_is_read(client: TestClient) -> None:
    response = client.post("/default", content=b"x" * MAX_REQUEST_BODY_BYTES)

    assert response.status_code == 200
    assert response.json() == {"length": MAX_REQUEST_BODY_BYTES}


def test_a_body_one_byte_over_the_limit_is_a_400_without_details(client: TestClient) -> None:
    response = client.post("/default", content=b"x" * (MAX_REQUEST_BODY_BYTES + 1))

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "invalid_request",
            "message": "the request is invalid",
            "retryable": False,
        }
    }


def test_an_empty_body_is_read_as_empty(client: TestClient) -> None:
    response = client.post("/small")

    assert response.json() == {"length": 0}


def test_a_chunked_body_over_the_limit_is_stopped_while_reading(client: TestClient) -> None:
    """`Content-Length` がなくても(chunked)、読みながら数えて打ち切る。"""
    chunks_sent: list[int] = []

    def chunks() -> Iterator[bytes]:
        for index in range(1_000):
            chunks_sent.append(index)
            yield b"x" * 4

    response = client.post("/small", content=chunks())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert "details" not in response.json()["error"]


def test_a_declared_length_over_the_limit_is_rejected_before_reading(client: TestClient) -> None:
    response = client.post("/small", content=b"x" * (SMALL_LIMIT + 1))

    assert response.status_code == 400


def make_request(headers: list[tuple[bytes, bytes]], body: bytes) -> Request:
    messages = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive() -> dict[str, object]:
        return messages.pop(0)

    scope = {"type": "http", "method": "POST", "path": "/", "headers": headers}
    return Request(scope, receive)


@pytest.mark.parametrize("length", [b"abc", b"-1", b"", "\u00b2".encode(), "\uff11\uff12".encode()])
def test_an_unusable_content_length_header_is_ignored_and_the_body_is_counted(
    length: bytes,
) -> None:
    """`isdigit()` は `²` も真にするが `int()` は失敗する。ASCII の数字だけを信じ、他は実測する。"""
    request = make_request([(b"content-length", length)], b"x" * 5)

    body = anyio.run(read_limited_body, request)

    assert body == b"x" * 5
