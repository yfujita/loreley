"""ローカル(127.0.0.1)の簡易 HTTP サーバ。実際の HTTP クライアントを通して確かめるテスト用。

`http.server` をスレッドで動かし、ポートは自動で割り当て(0)、テストの終了時に必ず止める。
受け取ったリクエスト(メソッド・パス・ヘッダ・本文)を記録し、応答はテストが関数で決める。
実際の Indexer・OpenSearch には接続しない。
"""

import json
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# `Reply.wait_for` の待ちの上限。テストの不具合で `Event` が立たなくても、ハンドラが残り続けない。
GATE_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class ReceivedRequest:
    method: str
    path: str  # パーセントエンコードされたまま
    headers: dict[str, str]  # 名前は小文字
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


@dataclass(frozen=True)
class Reply:
    status: int = 200
    body: Any = None  # JSON にして返す
    raw: bytes | None = None  # 指定すると `body` の代わりに、この生のバイト列を返す
    headers: dict[str, str] = field(default_factory=dict)
    # 指定すると、この `Event` が立つまで応答を返さない(上限 `GATE_TIMEOUT_SECONDS`)。
    # 待ち時間に頼らず、「応答が来ない間」を決定的に作る(クライアントのタイムアウトのテスト)。
    wait_for: threading.Event | None = None
    disconnect: bool = False  # 応答を返さずに接続を切る


@dataclass
class LocalServer:
    url: str
    requests: list[ReceivedRequest] = field(default_factory=list)


Responder = Callable[[ReceivedRequest], Reply]


@contextmanager
def local_http_server(respond: Responder) -> Iterator[LocalServer]:
    server_state = LocalServer(url="")

    class Handler(BaseHTTPRequestHandler):
        def handle_any(self) -> None:
            length = int(self.headers.get("content-length") or 0)
            request = ReceivedRequest(
                method=self.command,
                path=self.path,
                headers={name.lower(): value for name, value in self.headers.items()},
                body=self.rfile.read(length),
            )
            server_state.requests.append(request)
            reply = respond(request)
            if reply.disconnect:
                self.connection.close()
                return
            payload = (
                reply.raw
                if reply.raw is not None
                else json.dumps(reply.body if reply.body is not None else {}).encode()
            )
            if reply.wait_for is not None:
                reply.wait_for.wait(timeout=GATE_TIMEOUT_SECONDS)
            try:
                self.send_response(reply.status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                for name, value in reply.headers.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass  # タイムアウトで、クライアントが先に接続を閉じた

        do_GET = do_POST = do_PUT = do_DELETE = handle_any

        def log_message(self, format: str, *args: Any) -> None:
            """標準エラーに出さない。"""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server_state.url = f"http://127.0.0.1:{server.server_port}"
    # 既定の poll_interval(0.5 秒)だと、`shutdown()` の完了待ちが毎回最大 0.5 秒かかる。
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield server_state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), "the local server did not stop"
