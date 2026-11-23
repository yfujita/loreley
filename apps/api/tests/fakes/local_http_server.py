"""ローカルの HTTP スタブ(D 7.2)。実 HTTP で `crawler_client`・`probes` を確かめるための偽物。

127.0.0.1 の一時ポートで待ち受け、台本どおりの応答を返す。受けた**生のリクエスト行**(パスの
エンコードがそのまま見える)・ヘッダ・本文・回数・接続の数を記録する。

台本は `enqueue`(1 回分ずつ、順に消費)と `default_reply`(台本が尽きたときの応答)で決める。
応答の振る舞いは `StubReply` で、遅延・接続を閉じる(応答なし)・本文の途中で切る・リダイレクトなどを
表せる。接続拒否は、このスタブを止めた後のポート(`closed_port`)で再現する。
"""

import socket
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Literal

# `normal`: 通常の応答。`drop`: 要求を受けた後、何も返さずに接続を閉じる。
# `truncate`: 本文を `Content-Length` の長さより短く送って接続を閉じる(不完全な応答)。
ReplyMode = Literal["normal", "drop", "truncate"]


@dataclass(frozen=True)
class StubReply:
    status: int = 200
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)
    delay_seconds: float = 0.0
    mode: ReplyMode = "normal"


@dataclass(frozen=True)
class ReceivedRequest:
    request_line: str  # `POST /jobs/%2E%2E/cancel HTTP/1.1`(生のまま)
    method: str
    path: str  # リクエスト行のパス(生のまま)
    headers: Mapping[str, str]  # 名前は小文字
    body: bytes


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: "_StubServer"

    def do_GET(self) -> None:
        self._handle()

    do_POST = do_PUT = do_DELETE = do_GET

    def log_message(self, format: str, *args: object) -> None:
        """標準エラーに出さない。"""

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        self.server.record(
            ReceivedRequest(
                request_line=self.requestline,
                method=self.command,
                path=self.path,
                headers={name.lower(): value for name, value in self.headers.items()},
                body=body,
            )
        )
        reply = self.server.next_reply()
        # 台本の遅延は、サーバーを止めるときに打ち切れるよう、イベントで待つ。
        self.server.stopping.wait(reply.delay_seconds)
        if reply.mode == "drop":
            self.close_connection = True
            return
        self.send_response(reply.status)
        for name, value in reply.headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(reply.body) + _missing_bytes(reply)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(reply.body)
        self.close_connection = True


def _missing_bytes(reply: StubReply) -> int:
    """`truncate` のとき、宣言した長さと実際に送る長さの差(送らない分)。"""
    return 100 if reply.mode == "truncate" else 0


class _StubServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.stopping = threading.Event()
        self._lock = threading.Lock()
        self._requests: list[ReceivedRequest] = []
        self._replies: list[StubReply] = []
        self.default_reply = StubReply()
        self.connection_count = 0

    def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
        accepted = super().get_request()
        with self._lock:
            self.connection_count += 1
        return accepted

    def record(self, request: ReceivedRequest) -> None:
        with self._lock:
            self._requests.append(request)

    def next_reply(self) -> StubReply:
        with self._lock:
            return self._replies.pop(0) if self._replies else self.default_reply

    def add_reply(self, reply: StubReply) -> None:
        with self._lock:
            self._replies.append(reply)

    def snapshot_requests(self) -> list[ReceivedRequest]:
        with self._lock:
            return list(self._requests)


class LocalHttpServer:
    """`with local_http_server() as server:` で使う。"""

    def __init__(self, server: _StubServer) -> None:
        self._server = server

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def requests(self) -> list[ReceivedRequest]:
        return self._server.snapshot_requests()

    @property
    def connection_count(self) -> int:
        """受け付けた TCP 接続の数(接続を使い回していないことの確認用)。"""
        return self._server.connection_count

    def enqueue(self, *replies: StubReply) -> None:
        for reply in replies:
            self._server.add_reply(reply)

    def set_default_reply(self, reply: StubReply) -> None:
        self._server.default_reply = reply


@contextmanager
def local_http_server() -> Iterator[LocalHttpServer]:
    server = _StubServer()
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    thread.start()
    try:
        yield LocalHttpServer(server)
    finally:
        server.stopping.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def closed_port() -> int:
    """誰も待ち受けていないポート(接続拒否の再現用)。確保してすぐ閉じる。"""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
