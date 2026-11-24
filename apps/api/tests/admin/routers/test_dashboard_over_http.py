"""EP-13 を、実クライアント(`HttpHealthProbe`・`WebDistProbe`)とローカル HTTP スタブで確かめる。

偽のプローブでは見えない、実 HTTP での振る舞い(受けたメソッド・パス・回数、リダイレクトを追わない、
確認自身のタイムアウト、接続拒否、`web` のファイル)を、EP の応答まで通して確かめる(C 11章 10)。
`BlockingRunner` も実物(スレッドで実行)。OpenSearch の確認だけは、生のクライアントの偽物を使う。
"""

import io
import logging
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError
from urllib3.exceptions import NewConnectionError

from loreley_api.admin import AdminProbes, create_admin_app
from loreley_api.common.concurrency import BlockingRunner
from loreley_api.common.logging_setup import configure_logging
from loreley_api.infrastructure.opensearch import OpenSearchHealthProbe, ReadOnlyOpenSearch
from loreley_api.infrastructure.probes import HttpHealthProbe, HttpProbeConfig, WebDistProbe
from loreley_api.server import SubAppMount, create_app
from tests.admin.factories import ADMIN_PREFIX, make_admin_dependencies
from tests.api_config import make_admin_settings
from tests.fakes.clock import FixedClock
from tests.fakes.fake_opensearch_client import FakeOpenSearchClient
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.fakes.local_http_server import (
    LocalHttpServer,
    StubReply,
    closed_port,
    local_http_server,
)
from tests.secret_assertions import assert_secret_absent
from tests.timing import TIMING_SLACK_SECONDS

DASHBOARD = f"{ADMIN_PREFIX}/dashboard"
PROBE_TIMEOUT_SECONDS = 0.4
OPENSEARCH_HEALTH = {"cluster_name": "loreley", "status": "red"}


class RecordsCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def crawler_stub() -> Iterator[LocalHttpServer]:
    with local_http_server() as stub:
        yield stub


@pytest.fixture
def indexer() -> Iterator[LocalHttpServer]:
    with local_http_server() as stub:
        yield stub


@pytest.fixture
def web_dist(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    return tmp_path


def make_client(
    fake_opensearch: FakeOpenSearchClient, **settings: object
) -> tuple[TestClient, HttpHealthProbe]:
    http_probe = HttpHealthProbe(HttpProbeConfig(timeout_seconds=PROBE_TIMEOUT_SECONDS))
    deps = make_admin_dependencies(
        InMemoryReaders(),
        FixedClock(),
        BlockingRunner(),
        make_admin_settings(probe_timeout_seconds=PROBE_TIMEOUT_SECONDS, **settings),
        probes=AdminProbes(
            http=http_probe,
            opensearch=OpenSearchHealthProbe(ReadOnlyOpenSearch(fake_opensearch)),
            web_dist=WebDistProbe(),
        ),
    )
    app = create_app(mounts=[SubAppMount(ADMIN_PREFIX, create_admin_app(deps))])
    return TestClient(app), http_probe


def states_of(response_json: dict[str, object]) -> dict[str, tuple[str, str | None]]:
    components = response_json["components"]
    assert isinstance(components, list)
    return {c["id"]: (c["state"], c["reason"]) for c in components}


def test_every_component_is_normal_and_each_target_receives_one_get(
    crawler_stub: LocalHttpServer, indexer: LocalHttpServer, web_dist: Path
) -> None:
    fake_opensearch = FakeOpenSearchClient()
    fake_opensearch.script("cluster.health", OPENSEARCH_HEALTH)  # `red` でも応答できれば正常
    client, probe = make_client(
        fake_opensearch,
        crawler_url=crawler_stub.url,
        indexer_url=indexer.url,
        web_dist_dir=str(web_dist),
    )

    response = client.get(DASHBOARD)
    probe.close()

    assert response.status_code == 200
    assert states_of(response.json()) == {
        "crawler": ("normal", None),
        "indexer": ("normal", None),
        "opensearch": ("normal", None),
        "api": ("normal", None),
        "web": ("normal", None),
        "opensearch-dashboards": ("not_configured", None),
        "embedding": ("not_configured", None),
        "llm": ("not_configured", None),
    }
    for server in (crawler_stub, indexer):
        [request] = server.requests
        assert (request.method, request.path) == ("GET", "/healthz")


def test_failures_are_reported_per_component_with_the_documented_reasons(
    indexer: LocalHttpServer, web_dist: Path
) -> None:
    indexer.set_default_reply(StubReply(503))  # 起動前の Indexer
    fake_opensearch = FakeOpenSearchClient()
    fake_opensearch.script(
        "cluster.health", OpenSearchConnectionError("N/A", "x", NewConnectionError(None, "refused"))
    )
    client, probe = make_client(
        fake_opensearch,
        crawler_url=f"http://127.0.0.1:{closed_port()}",
        indexer_url=indexer.url,
        web_dist_dir=str(web_dist / "no-such-directory"),
    )

    response = client.get(DASHBOARD)
    probe.close()

    assert response.status_code == 200
    assert states_of(response.json()) == {
        "crawler": ("abnormal", "connection_refused"),
        "indexer": ("abnormal", "unexpected_status"),
        "opensearch": ("abnormal", "connection_refused"),
        "api": ("normal", None),
        "web": ("abnormal", "missing"),
        "opensearch-dashboards": ("not_configured", None),
        "embedding": ("not_configured", None),
        "llm": ("not_configured", None),
    }


@pytest.mark.usefixtures("unresolvable_invalid_hosts")
def test_an_unresolvable_host_is_abnormal_name_not_resolved(
    crawler_stub: LocalHttpServer, web_dist: Path
) -> None:
    fake_opensearch = FakeOpenSearchClient()
    fake_opensearch.script("cluster.health", OPENSEARCH_HEALTH)
    client, probe = make_client(
        fake_opensearch,
        crawler_url=crawler_stub.url,
        indexer_url="http://indexer.invalid:8000",
        web_dist_dir=str(web_dist),
    )

    response = client.get(DASHBOARD)
    probe.close()

    assert states_of(response.json())["indexer"] == ("abnormal", "name_not_resolved")


def test_a_redirect_from_an_optional_target_is_not_followed(
    crawler_stub: LocalHttpServer, indexer: LocalHttpServer, web_dist: Path
) -> None:
    """確認先が 3xx を返しても追わず、`unexpected_status`(別のサービスへ誘導されない)。"""
    fake_opensearch = FakeOpenSearchClient()
    fake_opensearch.script("cluster.health", OPENSEARCH_HEALTH)
    with local_http_server() as dashboards, local_http_server() as redirect_target:
        dashboards.set_default_reply(StubReply(302, headers={"Location": redirect_target.url}))
        client, probe = make_client(
            fake_opensearch,
            crawler_url=crawler_stub.url,
            indexer_url=indexer.url,
            web_dist_dir=str(web_dist),
            dashboards_health_url=f"{dashboards.url}/api/status",
        )

        response = client.get(DASHBOARD)
        probe.close()

        assert states_of(response.json())["opensearch-dashboards"] == (
            "abnormal",
            "unexpected_status",
        )
        assert [request.path for request in dashboards.requests] == ["/api/status"]
        assert redirect_target.requests == []
        assert redirect_target.connection_count == 0


def test_a_target_that_does_not_answer_is_undetermined_timeout_within_the_deadline(
    crawler_stub: LocalHttpServer, indexer: LocalHttpServer, web_dist: Path
) -> None:
    indexer.set_default_reply(StubReply(200, delay_seconds=10.0))
    fake_opensearch = FakeOpenSearchClient()
    fake_opensearch.script("cluster.health", OPENSEARCH_HEALTH)
    client, probe = make_client(
        fake_opensearch,
        crawler_url=crawler_stub.url,
        indexer_url=indexer.url,
        web_dist_dir=str(web_dist),
    )

    started_at = time.monotonic()
    response = client.get(DASHBOARD)
    elapsed_seconds = time.monotonic() - started_at
    probe.close()

    states = states_of(response.json())
    assert states["indexer"] == ("undetermined", "timeout")
    assert states["crawler"] == ("normal", None)
    # 確認先の遅延(10 秒)を待たずに戻る(確認自身のタイムアウトの検証は `test_http_probe.py`)。
    assert elapsed_seconds < PROBE_TIMEOUT_SECONDS + TIMING_SLACK_SECONDS
    assert len(indexer.requests) == 1  # 再送しない


@pytest.mark.usefixtures("restore_logging", "unresolvable_invalid_hosts")
def test_the_configured_urls_and_the_opensearch_error_are_in_neither_the_response_nor_the_logs(
    crawler_stub: LocalHttpServer, indexer: LocalHttpServer, web_dist: Path
) -> None:
    stream = io.StringIO()
    configure_logging(level="DEBUG", stream=stream)
    collector = RecordsCollector()
    logging.getLogger().addHandler(collector)
    token = "SENTINEL-HEALTH-TOKEN"
    opensearch_secret = "SENTINEL-OPENSEARCH-PASSWORD"
    indexer.set_default_reply(StubReply(500))
    fake_opensearch = FakeOpenSearchClient()
    fake_opensearch.script(
        "cluster.health",
        OpenSearchConnectionError(
            "N/A",
            f"http://elastic:{opensearch_secret}@opensearch.invalid:9200",
            NewConnectionError(None, f"refused {opensearch_secret}"),
        ),
    )
    client, probe = make_client(
        fake_opensearch,
        crawler_url=crawler_stub.url,
        indexer_url=indexer.url,
        web_dist_dir=str(web_dist),
        embedding_health_url=f"http://127.0.0.1:{closed_port()}/{token}?key={token}",
        llm_health_url=f"http://{token.lower()}.invalid/healthz",
    )

    response = client.get(DASHBOARD)
    probe.close()

    assert response.status_code == 200
    captured_text = stream.getvalue()
    assert "health probe finished" in captured_text  # ログが捕捉できている
    for secret in (token, token.lower(), opensearch_secret):
        assert_secret_absent(
            secret,
            response_text=response.text,
            records=collector.records,
            captured_text=captured_text,
        )
    for address in (crawler_stub.url, indexer.url):
        assert address not in response.text
