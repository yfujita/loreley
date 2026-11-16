"""接続エラー・タイムアウトと、API ごとのタイムアウト(architecture 7.10・11章)。

実際の接続の失敗(接続拒否・切断・応答の遅れ)はローカルのサーバで起こし、`urllib3` の例外の
分類は偽のプールで確かめる。
"""

import socket
import threading
from typing import Any

import pytest
import urllib3
from urllib3.exceptions import (
    ConnectTimeoutError,
    NewConnectionError,
    ProtocolError,
    ReadTimeoutError,
)

from loreley_crawler.infrastructure.indexer_client import (
    ApiTimeouts,
    BatchResults,
    Change,
    DocumentRegistered,
    HttpIndexerClient,
    IndexerClientConfig,
    IndexerUnavailable,
    Succeeded,
)
from tests.fakes.local_http_server import Reply, local_http_server
from tests.infrastructure.indexer_client.support import (
    DOCUMENT_ID,
    EXTERNAL_ID,
    LOCK,
    OPERATIONS,
    SOURCE_ID,
    call_with,
)

JOIN_TIMEOUT_SECONDS = 5.0
BATCH_ENTRY = {
    "external_id": EXTERNAL_ID,
    "document_id": DOCUMENT_ID,
    "status": "ok",
    "change": "created",
    "extract_failed": False,
}


def unused_local_port() -> int:
    """接続を受け付けないポート(取得して、すぐ閉じる)。"""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_a_refused_connection_is_unavailable_not_a_timeout() -> None:
    # `NewConnectionError` は `ConnectTimeoutError` の子クラスなので、取り違えやすい。
    client = HttpIndexerClient(IndexerClientConfig(f"http://127.0.0.1:{unused_local_port()}"))

    assert OPERATIONS["status"](client) == IndexerUnavailable("connection_error")


@pytest.mark.parametrize("operation", OPERATIONS.values(), ids=OPERATIONS.keys())
def test_a_connection_closed_without_a_response_is_unavailable_for_every_api(
    operation: Any,
) -> None:
    assert call_with(Reply(disconnect=True), operation) == IndexerUnavailable("connection_error")


def test_a_response_that_does_not_come_within_the_timeout_is_unavailable_as_a_timeout() -> None:
    gate = threading.Event()  # 開くまで、サーバは応答しない
    with local_http_server(lambda request: Reply(wait_for=gate)) as server:
        client = HttpIndexerClient(
            IndexerClientConfig(server.url, timeouts=ApiTimeouts(status=0.1))
        )
        try:
            assert OPERATIONS["status"](client) == IndexerUnavailable("timeout")
        finally:
            gate.set()


def test_each_api_uses_its_own_timeout() -> None:
    # 応答が来ない間、`last-seen`(0.1 秒)は間に合わず、同じ状況からのバッチ登録(3 秒)は、
    # 応答が来れば成功する(各 API のタイムアウトの対応は、下の記録つきのプールのテストで確かめる)。
    gate = threading.Event()
    reply = Reply(body={"results": [BATCH_ENTRY]}, wait_for=gate)
    timeouts = ApiTimeouts(last_seen=0.1, register_batch=3.0)
    with local_http_server(lambda request: reply) as server:
        client = HttpIndexerClient(IndexerClientConfig(server.url, timeouts=timeouts))
        opener = threading.Timer(0.5, gate.set)  # 3 秒の待ちより十分早く、応答を許す
        try:
            assert OPERATIONS["last_seen"](client) == IndexerUnavailable("timeout")
            opener.start()
            batch_reply = OPERATIONS["batch"](client)
        finally:
            gate.set()
            opener.cancel()
            opener.join(timeout=JOIN_TIMEOUT_SECONDS)

    assert batch_reply == BatchResults(
        documents=(DocumentRegistered(EXTERNAL_ID, DOCUMENT_ID, Change.CREATED, False),)
    )


class RecordingPool:
    """`request` に渡されたタイムアウトを記録する偽のプール。"""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "url": url, **kwargs})
        if self.error is not None:
            raise self.error
        raise AssertionError("not reached in these tests")

    def clear(self) -> None:
        pass


TIMEOUTS = ApiTimeouts(
    start=1.0,
    finish=2.0,
    status=3.0,
    last_seen=4.0,
    register_batch=5.0,
    discard_deletions=6.0,
    delete_documents=7.0,
    delete_deletion_records=8.0,
)


@pytest.mark.parametrize(
    ("operation", "read_timeout_seconds"),
    [
        ("start", 1.0),
        ("finish", 2.0),
        ("status", 3.0),
        ("last_seen", 4.0),
        ("batch", 5.0),
        ("discard", 6.0),
        ("delete_documents", 7.0),
        ("delete_records", 8.0),
    ],
)
def test_every_api_passes_its_own_read_timeout_and_the_common_connect_timeout(
    operation: str, read_timeout_seconds: float
) -> None:
    pool = RecordingPool(error=ReadTimeoutError(None, "x", "timed out"))
    client = HttpIndexerClient(
        IndexerClientConfig("http://indexer:8000", timeouts=TIMEOUTS, connect_timeout_seconds=9.0),
        pool=pool,
    )

    assert OPERATIONS[operation](client) == IndexerUnavailable("timeout")

    [call] = pool.calls
    timeout: urllib3.Timeout = call["timeout"]
    assert (timeout.connect_timeout, timeout.read_timeout) == (9.0, read_timeout_seconds)
    # リトライ・リダイレクトはしない(リトライは確認点つきで、呼び出し側が行う)。
    assert call["retries"] is False
    assert call["redirect"] is False


def test_the_default_timeouts_are_the_provisional_values_of_architecture_11() -> None:
    assert ApiTimeouts() == ApiTimeouts(
        start=30.0,
        finish=30.0,
        status=30.0,
        last_seen=60.0,
        register_batch=300.0,
        discard_deletions=600.0,
        delete_documents=4_200.0,
        delete_deletion_records=60.0,
    )


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ReadTimeoutError(None, "x", "timed out"), "timeout"),
        (ConnectTimeoutError(None, "timed out"), "timeout"),
        (NewConnectionError(None, "refused"), "connection_error"),
        (ProtocolError("Connection aborted."), "connection_error"),
        (urllib3.exceptions.SSLError("handshake failed"), "connection_error"),
        (urllib3.exceptions.HTTPError("anything else"), "connection_error"),
    ],
)
def test_urllib3_errors_are_classified_as_timeout_or_connection_error(
    error: Exception, reason: str
) -> None:
    pool = RecordingPool(error=error)
    client = HttpIndexerClient(IndexerClientConfig("http://indexer:8000"), pool=pool)

    assert OPERATIONS["status"](client) == IndexerUnavailable(reason)


def test_an_unrelated_programming_error_is_not_swallowed() -> None:
    pool = RecordingPool(error=RuntimeError("bug"))
    client = HttpIndexerClient(IndexerClientConfig("http://indexer:8000"), pool=pool)

    with pytest.raises(RuntimeError, match="bug"):
        OPERATIONS["status"](client)


def test_the_client_recovers_after_a_failure_on_the_same_connection_pool() -> None:
    replies = iter([Reply(disconnect=True), Reply(body={"crawl_id": "j", "status": "running"})])
    with local_http_server(lambda request: next(replies)) as server:
        client = HttpIndexerClient(IndexerClientConfig(server.url))

        first = OPERATIONS["start"](client)
        second = OPERATIONS["start"](client)

    assert first == IndexerUnavailable("connection_error")
    assert second == Succeeded()


def test_the_lock_is_sent_even_when_the_server_closes_the_connection_midway() -> None:
    with local_http_server(lambda request: Reply(disconnect=True)) as server:
        client = HttpIndexerClient(IndexerClientConfig(server.url))

        result = client.delete_documents(SOURCE_ID, lock=LOCK)

        assert result == IndexerUnavailable("connection_error")
        assert server.requests[0].json() == {"lock": {"owner": LOCK.owner, "job_id": LOCK.job_id}}


# --- 設定の検証 ---


@pytest.mark.parametrize(
    "url",
    [
        "indexer:8000",
        "ftp://indexer:8000",
        "http://",
        "http://user:SENTINEL-PASSWORD@indexer:8000",
        "http://indexer:8000/api",
        "http://indexer:8000?x=1",
        "http://indexer:notaport",
    ],
)
def test_an_invalid_indexer_url_is_rejected_without_echoing_it(url: str) -> None:
    with pytest.raises(ValueError, match="Indexer URL") as excinfo:
        IndexerClientConfig(url)

    assert "SENTINEL-PASSWORD" not in str(excinfo.value)


def test_a_trailing_slash_in_the_base_url_does_not_double_the_slash() -> None:
    with local_http_server(
        lambda request: Reply(body={"crawl_id": "j", "source_id": "s", "status": "running"})
    ) as server:
        client = HttpIndexerClient(IndexerClientConfig(server.url + "/"))

        OPERATIONS["status"](client)

        assert server.requests[0].path == "/crawls/job-20261113-0a1b2c3d"


@pytest.mark.parametrize("overrides", [{"status": 0.0}, {"delete_documents": -1.0}])
def test_non_positive_api_timeouts_are_rejected(overrides: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        ApiTimeouts(**overrides)


def test_a_non_positive_connect_timeout_is_rejected() -> None:
    with pytest.raises(ValueError, match="connect_timeout_seconds"):
        IndexerClientConfig("http://indexer:8000", connect_timeout_seconds=0)
