"""本文の上限(A 5.1。1 MiB)。超過は 400 `invalid_request`(`details` なし)。"""

import logging
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

    @app.post("/items/{item_id}")
    async def read_item(item_id: str, request: Request) -> dict[str, int]:
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


# --- 読み取りの途中の切断(`ClientDisconnect`。D 4.12(c)) ---


def disconnect_during_body(app: FastAPI, path: str = "/default") -> list[dict[str, object]]:
    """本文を読む POST で、読み取りの途中にクライアントが切断した状況を ASGI で再現する。

    `TestClient` は切断を作れないので、`receive` が `http.disconnect` を返す形で呼ぶ。
    """
    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"transfer-encoding", b"chunked")],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    anyio.run(app, scope, receive, send)
    return sent


def test_a_disconnect_while_reading_is_a_warning_and_a_400_not_an_error_and_a_500(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    sent = disconnect_during_body(client.app)  # type: ignore[arg-type]

    statuses = [message["status"] for message in sent if message["type"] == "http.response.start"]
    assert statuses == [400]
    records = [r for r in caplog.records if r.name.startswith("loreley_api")]
    assert [(r.levelno, r.name) for r in records if r.levelno >= logging.WARNING] == [
        (logging.WARNING, "loreley_api.common.http.body")
    ]
    access_lines = [r.getMessage() for r in records if r.name == "loreley_api.access"]
    assert len(access_lines) == 1
    assert access_lines[0].startswith("POST /default 400 ")


DISCONNECT_WARNING = "the client disconnected while the request body was being read"


def test_the_disconnect_warning_is_a_fixed_sentence_without_values_or_the_exception(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """リクエストの値(パス中の ID など)・例外の内容・トレースバックを、ログに出さない。"""
    caplog.set_level(logging.DEBUG)
    secret_path = "/items/SENTINEL-ITEM-ID"

    disconnect_during_body(client.app, secret_path)  # type: ignore[arg-type]

    warnings = [
        r
        for r in caplog.records
        if r.name == "loreley_api.common.http.body" and r.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    assert warnings[0].getMessage() == DISCONNECT_WARNING
    assert warnings[0].args in ((), None)  # 値を差し込む引数がない
    assert warnings[0].exc_info is None  # 例外の内容・トレースバックを出さない
    assert "SENTINEL" not in repr(vars(warnings[0]))
    non_access_records = [r for r in caplog.records if r.name != "loreley_api.access"]
    assert all("SENTINEL" not in repr(vars(r)) for r in non_access_records)


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError, OSError])
def test_a_read_error_other_than_a_disconnect_is_not_turned_into_a_400(
    error_type: type[Exception],
) -> None:
    """切断以外の失敗(想定外の異常)は、そのまま伝播する。400 にすると本物の異常を隠す。"""

    async def receive() -> dict[str, object]:
        raise error_type("unexpected")

    request = Request({"type": "http", "method": "POST", "path": "/", "headers": []}, receive)

    with pytest.raises(error_type, match="unexpected"):
        anyio.run(read_limited_body, request)
