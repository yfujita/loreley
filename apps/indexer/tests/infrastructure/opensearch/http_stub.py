"""実際の `OpenSearch` クライアントをつなぐ、ローカルの HTTP スタブ(127.0.0.1 のみ)。

通信層(ライブラリが出すログ・例外)を通して確かめるテスト用。ポートは自動で割り当て、
テストの終了時に必ず止める。実際の OpenSearch には接続しない。
"""

import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass(frozen=True)
class StubResponse:
    status: int = 200
    body: Any = None  # JSON にして返す
    raw: bytes | None = (
        None  # 指定すると `body` の代わりに、この生のバイト列を返す(壊れた JSON など)
    )
    content_type: str = "application/json"
    disconnect: bool = False  # 応答を返さずに接続を切る
    delay_seconds: float = 0.0  # 応答を返すまでの待ち(クライアントのタイムアウトを起こす)


@dataclass
class StubOpenSearch:
    url: str
    requests: list[tuple[str, str, bytes]] = field(default_factory=list)  # (メソッド, パス, 本文)


Responder = Callable[[str, str], StubResponse]


@contextmanager
def stub_opensearch(respond: Responder) -> Iterator[StubOpenSearch]:
    """`respond(メソッド, パス)` の返す応答を、すべてのリクエストに返すサーバを起動する。"""
    stub = StubOpenSearch(url="")

    class Handler(BaseHTTPRequestHandler):
        def handle_any(self) -> None:
            length = int(self.headers.get("content-length") or 0)
            stub.requests.append((self.command, self.path, self.rfile.read(length)))
            response = respond(self.command, self.path)
            if response.disconnect:
                self.connection.close()
                return
            payload = (
                response.raw
                if response.raw is not None
                else json.dumps(response.body if response.body is not None else {}).encode()
            )
            time.sleep(response.delay_seconds)
            try:
                self.send_response(response.status)
                self.send_header("content-type", response.content_type)
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass  # タイムアウトで、クライアントが先に接続を閉じた

        do_GET = do_POST = do_PUT = do_DELETE = handle_any

        def log_message(self, format: str, *args: Any) -> None:
            """標準エラーに出さない。"""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    stub.url = f"http://127.0.0.1:{server.server_port}"
    # 既定の poll_interval(0.5 秒)だと、`shutdown()` の完了待ちが毎回最大 0.5 秒かかる。
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield stub
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), "the stub server did not stop"
