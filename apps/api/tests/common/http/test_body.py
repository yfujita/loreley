"""本文の上限(A 5.1。1 MiB)。超過は 400 `invalid_request`(`details` なし)。"""

from collections.abc import Iterator
from functools import partial

import anyio
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from loreley_api.common.http import ApiError, install_common_http
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


def test_a_chunked_body_over_the_limit_is_a_400_without_details(client: TestClient) -> None:
    """`Content-Length` がなくても(chunked)、読みながら数えて上限を超えたら 400 にする。"""

    def chunks() -> Iterator[bytes]:
        # 1 バイトずつ送り、上限(SMALL_LIMIT)を 1 バイトだけ超える。
        for _ in range(SMALL_LIMIT + 1):
            yield b"x"

    response = client.post("/small", content=chunks())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert "details" not in response.json()["error"]


class RecordingReceive:
    """ASGI の `receive` の偽物。呼ばれた回数を数え、`chunks` を 1 つずつ返す。"""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.num_calls = 0

    async def __call__(self) -> dict[str, object]:
        index = self.num_calls
        self.num_calls += 1
        return {
            "type": "http.request",
            "body": self._chunks[index],
            "more_body": index < len(self._chunks) - 1,
        }


def make_request(
    headers: list[tuple[bytes, bytes]], chunks: list[bytes]
) -> tuple[Request, RecordingReceive]:
    receive = RecordingReceive(chunks)
    scope = {"type": "http", "method": "POST", "path": "/", "headers": headers}
    return Request(scope, receive), receive


def test_a_chunked_body_over_the_limit_stops_reading_at_the_first_chunk_over() -> None:
    chunk_size = 4
    num_chunks_until_over = SMALL_LIMIT // chunk_size + 1
    request, receive = make_request([], [b"x" * chunk_size] * 1_000)

    with pytest.raises(ApiError):
        anyio.run(partial(read_limited_body, request, max_bytes=SMALL_LIMIT))

    assert receive.num_calls == num_chunks_until_over  # 超過後に、残りの本文を読み続けない


def test_a_declared_length_over_the_limit_is_rejected_without_reading() -> None:
    request, receive = make_request(
        [(b"content-length", str(SMALL_LIMIT + 1).encode())], [b"x" * (SMALL_LIMIT + 1)]
    )

    with pytest.raises(ApiError):
        anyio.run(partial(read_limited_body, request, max_bytes=SMALL_LIMIT))

    assert receive.num_calls == 0


def test_a_declared_length_at_the_limit_is_read() -> None:
    request, receive = make_request(
        [(b"content-length", str(SMALL_LIMIT).encode())], [b"x" * SMALL_LIMIT]
    )

    body = anyio.run(partial(read_limited_body, request, max_bytes=SMALL_LIMIT))

    assert body == b"x" * SMALL_LIMIT
    assert receive.num_calls == 1


def test_a_declared_length_over_the_limit_is_a_400(client: TestClient) -> None:
    response = client.post("/small", content=b"x" * (SMALL_LIMIT + 1))

    assert response.status_code == 400


@pytest.mark.parametrize("num_digits", [20, 4_300, 100_000])
def test_a_declared_length_with_too_many_digits_is_over_the_limit_not_a_server_error(
    num_digits: int,
) -> None:
    """`int()` は 4,300 桁超で `ValueError`(500)になる。桁数で先に上限超過とする。"""
    request, receive = make_request([(b"content-length", b"9" * num_digits)], [b""])

    with pytest.raises(ApiError):
        anyio.run(read_limited_body, request)

    assert receive.num_calls == 0


def test_leading_zeros_do_not_make_a_small_declared_length_over_the_limit() -> None:
    request, _ = make_request([(b"content-length", b"0" * 5_000 + b"5")], [b"x" * 5])

    body = anyio.run(read_limited_body, request)

    assert body == b"x" * 5


@pytest.mark.parametrize("length", [b"abc", b"-1", b"", "\u00b2".encode(), "\uff11\uff12".encode()])
def test_an_unusable_content_length_header_is_ignored_and_the_body_is_counted(
    length: bytes,
) -> None:
    """`isdigit()` は `²` も真にするが `int()` は失敗する。ASCII の数字だけを信じ、他は実測する。"""
    request, _ = make_request([(b"content-length", length)], [b"x" * 5])

    body = anyio.run(read_limited_body, request)

    assert body == b"x" * 5
