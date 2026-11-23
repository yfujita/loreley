"""`HttpHealthProbe` を、ローカル HTTP スタブで確かめる(C 6.1・6.2・6.4。C 11章 8(e)・10)。

実 HTTP のため、受けたメソッド・パス・回数・ヘッダ(リダイレクト先に届かないこと)を確かめられる。
接続拒否は閉じたポート、名前解決の失敗は `.invalid` のホストで再現する。
"""

import io
import logging
import time
from collections.abc import Iterator

import pytest

from loreley_api.common.logging_setup import configure_logging
from loreley_api.common.probe_outcome import ProbeOutcome
from loreley_api.infrastructure.probes import HttpHealthProbe, HttpProbeConfig
from tests.fakes.local_http_server import (
    LocalHttpServer,
    StubReply,
    closed_port,
    local_http_server,
)
from tests.secret_assertions import assert_secret_absent

TIMEOUT_SECONDS = 0.4
# 待たされた確認が、確認自身のタイムアウトで戻ることの確認に使う、スタブの遅延。
LONG_DELAY_SECONDS = 5.0
NORMAL = ProbeOutcome("normal", None)


class RecordsCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def server() -> Iterator[LocalHttpServer]:
    with local_http_server() as stub:
        yield stub


@pytest.fixture
def probe() -> Iterator[HttpHealthProbe]:
    created = HttpHealthProbe(HttpProbeConfig(timeout_seconds=TIMEOUT_SECONDS))
    yield created
    created.close()


@pytest.mark.parametrize("status", [200, 204])
def test_a_2xx_response_is_normal(
    server: LocalHttpServer, probe: HttpHealthProbe, status: int
) -> None:
    server.set_default_reply(StubReply(status, b'{"status": "ok"}'))

    assert probe.check(f"{server.url}/healthz") == NORMAL


@pytest.mark.parametrize("status", [400, 404, 500, 503])
def test_a_response_outside_2xx_is_abnormal_unexpected_status(
    server: LocalHttpServer, probe: HttpHealthProbe, status: int
) -> None:
    server.set_default_reply(StubReply(status))

    assert probe.check(f"{server.url}/healthz") == ProbeOutcome("abnormal", "unexpected_status")


def test_the_request_is_a_get_for_exactly_the_given_url_sent_once(
    server: LocalHttpServer, probe: HttpHealthProbe
) -> None:
    probe.check(f"{server.url}/healthz")

    [request] = server.requests
    assert (request.method, request.path) == ("GET", "/healthz")
    assert request.body == b""
    # 接続を使い回さない(閉じられた接続の再利用で、動いているのに失敗に見えないように)。
    assert request.headers["connection"] == "close"
    assert server.connection_count == 1


def test_a_full_url_of_an_optional_component_is_requested_as_given(
    server: LocalHttpServer, probe: HttpHealthProbe
) -> None:
    probe.check(f"{server.url}/api/status?probe=1")

    assert [request.path for request in server.requests] == ["/api/status?probe=1"]


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_a_redirect_is_not_followed_and_is_unexpected_status(
    server: LocalHttpServer, probe: HttpHealthProbe, status: int
) -> None:
    """確認先を、内部の別のサービスへ誘導されない(SSRF の予防。C 6.1)。"""
    with local_http_server() as redirect_target:
        server.set_default_reply(StubReply(status, headers={"Location": redirect_target.url}))

        outcome = probe.check(f"{server.url}/healthz")

        assert outcome == ProbeOutcome("abnormal", "unexpected_status")
        assert len(server.requests) == 1
        assert redirect_target.requests == []
        assert redirect_target.connection_count == 0


def test_the_body_is_not_read(server: LocalHttpServer, probe: HttpHealthProbe) -> None:
    """宣言した長さより短い本文(読むと不完全な応答になる)でも、状態行だけで判定して正常。"""
    server.set_default_reply(StubReply(200, b"partial", mode="truncate"))

    assert probe.check(f"{server.url}/healthz") == NORMAL


def test_a_refused_connection_is_abnormal_connection_refused(probe: HttpHealthProbe) -> None:
    assert probe.check(f"http://127.0.0.1:{closed_port()}/healthz") == ProbeOutcome(
        "abnormal", "connection_refused"
    )


def test_an_unresolvable_host_is_abnormal_name_not_resolved(probe: HttpHealthProbe) -> None:
    assert probe.check("http://indexer.invalid:8000/healthz") == ProbeOutcome(
        "abnormal", "name_not_resolved"
    )


def test_no_response_within_the_timeout_is_undetermined_timeout_and_returns_in_time(
    server: LocalHttpServer, probe: HttpHealthProbe
) -> None:
    server.set_default_reply(StubReply(200, delay_seconds=LONG_DELAY_SECONDS))

    started_at = time.monotonic()
    outcome = probe.check(f"{server.url}/healthz")
    elapsed_seconds = time.monotonic() - started_at

    assert outcome == ProbeOutcome("undetermined", "timeout")
    # 接続と読み取りの合計(`Timeout(total=…)`)に収まる。再送もしない。
    assert elapsed_seconds < TIMEOUT_SECONDS + 1.0
    assert len(server.requests) == 1


def test_a_connection_closed_without_a_response_is_undetermined_connection_error(
    server: LocalHttpServer, probe: HttpHealthProbe
) -> None:
    server.set_default_reply(StubReply(mode="drop"))

    outcome = probe.check(f"{server.url}/healthz")

    assert outcome == ProbeOutcome("undetermined", "connection_error")
    assert len(server.requests) == 1  # 再送しない


def test_a_malformed_url_is_undetermined_connection_error_not_an_exception(
    probe: HttpHealthProbe,
) -> None:
    assert probe.check("http://") == ProbeOutcome("undetermined", "connection_error")


@pytest.mark.usefixtures("restore_logging")
def test_the_url_is_not_written_to_the_logs_even_at_debug(server: LocalHttpServer) -> None:
    """本番と同じログ設定(urllib3 のロガーは ERROR 以上)で、DEBUG でも URL を出さない(R11)。"""
    stream = io.StringIO()
    configure_logging(level="DEBUG", stream=stream)
    collector = RecordsCollector()
    logging.getLogger().addHandler(collector)
    secret = "SENTINEL-PROBE-TOKEN"
    server.set_default_reply(StubReply(500))
    probe = HttpHealthProbe(HttpProbeConfig(timeout_seconds=TIMEOUT_SECONDS))

    probe.check(f"{server.url}/healthz?token={secret}")
    probe.check(f"http://127.0.0.1:{closed_port()}/{secret}")
    probe.check(f"http://{secret.lower()}.invalid/healthz")

    captured_text = stream.getvalue()
    assert "health probe finished: state=abnormal" in captured_text  # 捕捉できている
    for sentinel in (secret, secret.lower()):
        assert_secret_absent(sentinel, records=collector.records, captured_text=captured_text)
