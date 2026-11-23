import logging
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from loreley_api.infrastructure.opensearch import ReadOnlyConnection, ReadOnlyOpenSearch
from loreley_api.main import ADMIN_API_PREFIX, build_app, build_lifespan, close_all, main
from tests.api_config import SENTINEL_PASSWORD, make_api_config
from tests.fakes.fake_opensearch_client import FakeOpenSearchClient
from tests.infrastructure.opensearch.sample_responses import (
    hit,
    mget_doc,
    mget_response,
    msearch_response,
    search_response,
)
from tests.log_records import server_side_text
from tests.secret_assertions import assert_secret_absent

SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
SENTINEL_PORT = "SENTINEL-PORT"
REQUIRED_ENVIRONMENT = {
    "opensearch_url": "http://opensearch.invalid:9200",
    "crawler_url": "http://crawler.invalid:8001",
    "indexer_url": "http://indexer.invalid:8000",
}


@pytest.fixture
def forbid_network_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    """組み立てが外部に接続しないことの確認用。接続や名前解決を試みたらテストを失敗させる。"""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"unexpected network access: {args!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def test_the_built_app_serves_the_health_check() -> None:
    response = TestClient(build_app(make_api_config())).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_built_app_answers_an_unknown_path_with_a_json_404() -> None:
    response = TestClient(build_app(make_api_config())).get("/nope")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert response.json()["error"]["code"] == "not_found"


def test_the_admin_api_is_mounted_and_answers_an_unknown_path_with_a_json_404() -> None:
    response = TestClient(build_app(make_api_config())).get(f"{ADMIN_API_PREFIX}/NO-SUCH-PATH")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "error": {"code": "not_found", "message": "the path is not defined", "retryable": False}
    }


def test_the_admin_api_has_no_documentation_or_openapi_by_default() -> None:
    client = TestClient(build_app(make_api_config()))

    for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
        for prefix in ("", ADMIN_API_PREFIX):
            response = client.get(prefix + path)
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "not_found"


def test_the_access_log_of_the_admin_api_uses_the_dash_for_an_unknown_path(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    TestClient(build_app(make_api_config())).get(f"{ADMIN_API_PREFIX}/SENTINEL-ID")

    lines = [r.getMessage() for r in caplog.records if r.name == "loreley_api.access"]
    assert len(lines) == 1
    assert lines[0].startswith("GET - 404 ")
    assert "SENTINEL" not in lines[0]


def test_building_and_running_the_app_makes_no_network_access(
    forbid_network_connections: None,
) -> None:
    """組み立てと、lifespan(開始・終了)の実行まで、外部に接続しない。"""
    with TestClient(build_app(make_api_config())) as client:
        assert client.get("/healthz").status_code == 200


def test_the_secret_password_is_in_neither_the_responses_nor_the_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """lifespan の開始・終了と、未知のパス(外側・Admin のマウント内)の 404 を通して確かめる。"""
    caplog.set_level(logging.DEBUG)
    response_texts: list[str] = []

    with TestClient(build_app(make_api_config())) as client:
        for path in ("/healthz", "/nope", f"{ADMIN_API_PREFIX}/NO-SUCH-PATH"):
            response_texts.append(client.get(path).text)

    assert any("not_found" in text for text in response_texts)  # 404 の本文も対象に入っている
    assert_secret_absent(
        SENTINEL_PASSWORD, response_text="".join(response_texts), records=caplog.records
    )


def test_the_health_check_is_logged_at_debug_and_other_paths_at_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`debug_access_log_paths` の配線(`/healthz` は数秒おきに呼ばれるので DEBUG)。"""
    caplog.set_level(logging.DEBUG)
    client = TestClient(build_app(make_api_config()))

    client.get("/healthz")
    client.get("/nope")

    levels = [
        (record.getMessage().split(" ")[1], record.levelno)
        for record in caplog.records
        if record.name == "loreley_api.access"
    ]
    assert levels == [("/healthz", logging.DEBUG), ("-", logging.INFO)]


# --- Admin API の配線(Reader・索引名・クライアントの停止) ---


@pytest.fixture
def fake_opensearch(monkeypatch: pytest.MonkeyPatch) -> FakeOpenSearchClient:
    """OpenSearch の読み取り用クライアントを偽物に差し替える(組み立ては本物の Reader)。"""
    fake = FakeOpenSearchClient()
    connection = ReadOnlyConnection(client=ReadOnlyOpenSearch(fake), close=fake.close)
    monkeypatch.setattr("loreley_api.main.create_read_connection", lambda config: connection)
    return fake


def test_the_admin_api_reads_the_job_through_the_configured_indices(
    fake_opensearch: FakeOpenSearchClient,
) -> None:
    job = {"record_type": "job", "source_id": "docs", "job_type": "crawl", "status": "succeeded"}
    fake_opensearch.script("mget", mget_response(mget_doc("job-1", job)))
    fake_opensearch.script("search", search_response([hit("job-1")]))
    fake_opensearch.script("mget", mget_response(mget_doc("deletion_result-job-1", found=False)))

    response = TestClient(build_app(make_api_config())).get(f"{ADMIN_API_PREFIX}/jobs/job-1")

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert [request.index for request in fake_opensearch.requests] == [
        "loreley-jobs",
        "loreley-jobs",
        "loreley-deletions",
    ]


def test_the_admin_api_lists_the_sources_through_the_configured_indices(
    fake_opensearch: FakeOpenSearchClient,
) -> None:
    fake_opensearch.script(
        "search",
        search_response(
            [hit("docs", {"connector_type": "file_system", "status": "active"})], total=1
        ),
    )
    fake_opensearch.script("search", search_response(aggregations={"by_source": {"buckets": []}}))
    fake_opensearch.script(
        "search",
        search_response(
            total=2, aggregations={"by_source": {"buckets": [{"key": "docs", "doc_count": 2}]}}
        ),
    )

    response = TestClient(build_app(make_api_config())).get(f"{ADMIN_API_PREFIX}/sources")

    assert response.status_code == 200
    [item] = response.json()["items"]
    assert (item["source_id"], item["document_count"], item["last_crawl"]) == ("docs", 2, None)
    # 設定・ジョブは `loreley-*`、登録文書数は検索インデックスのエイリアスを読む。
    assert [request.index for request in fake_opensearch.requests] == [
        "loreley-sources",
        "loreley-jobs",
        "loreley-documents",
    ]


def test_the_admin_api_reads_the_documents_of_a_source_through_the_configured_indices(
    fake_opensearch: FakeOpenSearchClient,
) -> None:
    fake_opensearch.script("mget", mget_response(mget_doc("docs", {})))
    fake_opensearch.script(
        "search",
        search_response(
            [hit("skip-docs-doc-1", {"document_id": "doc-1", "stage": "fetch"})], total=1
        ),
    )
    # 件数の対象の順: `document_count`、`extract_failed`、`oversize`、`summary_pending`。
    fake_opensearch.script(
        "msearch",
        msearch_response(
            search_response(total=5),
            search_response(total=2),
            search_response(total=1),
            search_response(total=0),
        ),
    )
    fake_opensearch.script("search", search_response([hit("doc-1")]))

    response = TestClient(build_app(make_api_config())).get(
        f"{ADMIN_API_PREFIX}/sources/docs/documents", params={"tab": "skipped"}
    )

    assert response.status_code == 200
    body = response.json()
    assert [(row["document_id"], row["existence"]) for row in body["items"]] == [
        ("doc-1", "existing")
    ]
    assert body["tab_counts"] == {
        "skipped": 1,
        "extract_failed": 2,
        "oversize": 1,
        "summary_pending": 0,
    }
    assert body["document_count"] == 5
    assert [request.index for request in fake_opensearch.requests] == [
        "loreley-sources",
        "loreley-jobs",
        None,  # msearch は、サブ要求ごとに索引を指定する
        "loreley-documents",
    ]
    [msearch] = fake_opensearch.requests_of("msearch")
    assert [header["index"] for header in msearch.body[::2]] == [  # type: ignore[index]
        "loreley-documents",
        "loreley-documents",
        "loreley-jobs",
        "loreley-documents",
    ]


def test_the_admin_api_reads_the_cluster_and_serves_the_meta_from_the_settings(
    fake_opensearch: FakeOpenSearchClient,
) -> None:
    fake_opensearch.script(
        "cluster.health",
        {
            "cluster_name": "loreley",
            "status": "green",
            "number_of_nodes": 1,
            "active_shards": 1,
            "relocating_shards": 0,
            "initializing_shards": 0,
            "unassigned_shards": 0,
        },
    )
    fake_opensearch.script("cat.indices", [{"index": "a", "health": "green", "docs.count": "3"}])
    fake_opensearch.script("cat.shards", [])
    fake_opensearch.script("cat.nodes", [{"name": "node-1"}])
    client = TestClient(build_app(make_api_config()))

    cluster = client.get(f"{ADMIN_API_PREFIX}/opensearch/cluster")
    meta = client.get(f"{ADMIN_API_PREFIX}/meta")

    assert cluster.status_code == 200
    assert cluster.json()["indices"] == [{"name": "a", "status": "green", "document_count": 3}]
    assert meta.json() == {"cron_timezone": "Asia/Tokyo", "dashboards_url": None}


def test_the_opensearch_client_is_closed_when_the_app_stops(
    fake_opensearch: FakeOpenSearchClient,
) -> None:
    with TestClient(build_app(make_api_config())):
        assert fake_opensearch.close_count == 0

    assert fake_opensearch.close_count == 1


# --- main()(uvicorn を差し替える。実際には起動しない) ---


def test_main_runs_uvicorn_once_with_the_settings_and_without_workers_or_reload(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    for name, value in REQUIRED_ENVIRONMENT.items():
        monkeypatch.setenv(f"LORELEY_API_{name.upper()}", value)
    monkeypatch.setenv("LORELEY_API_HOST", "0.0.0.0")
    monkeypatch.setenv("LORELEY_API_PORT", "9090")
    monkeypatch.setenv("LORELEY_API_LOG_LEVEL", "DEBUG")
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append((args, kwargs)))

    main()

    [(args, kwargs)] = calls
    [app] = args
    assert isinstance(app, FastAPI)
    # `workers`・`reload` などがない = 単一プロセス(ワーカー数 1)。
    assert kwargs == {"host": "0.0.0.0", "port": 9090, "log_config": None, "access_log": False}
    assert logging.getLogger().level == logging.DEBUG  # `configure_logging` が呼ばれた


def test_main_does_not_set_a_graceful_shutdown_timeout(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    """`timeout_graceful_shutdown` は指定しない(Indexer と同じ。AAM-P-28)。"""
    for name, value in REQUIRED_ENVIRONMENT.items():
        monkeypatch.setenv(f"LORELEY_API_{name.upper()}", value)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append(kwargs))

    main()

    assert "timeout_graceful_shutdown" not in calls[0]
    assert "lifespan" not in calls[0]  # uvicorn の既定(auto)で、外側の lifespan が実行される


# --- 停止時にクライアントを閉じる(外側の lifespan) ---


def test_the_clients_are_closed_when_the_app_stops() -> None:
    closed: list[str] = []
    app = FastAPI(lifespan=build_lifespan([lambda: closed.append("a"), lambda: closed.append("b")]))

    with TestClient(app):
        assert closed == []

    assert closed == ["a", "b"]


def test_a_failing_close_does_not_stop_the_others_and_logs_only_the_class_name(
    caplog: pytest.LogCaptureFixture,
) -> None:
    closed: list[str] = []

    def fail() -> None:
        raise OSError("SENTINEL-CLOSE-MESSAGE")

    close_all([lambda: closed.append("first"), fail, lambda: closed.append("last")])

    assert closed == ["first", "last"]
    [record] = caplog.records
    assert record.levelno == logging.ERROR
    assert "OSError" in record.getMessage()
    assert "SENTINEL" not in server_side_text(caplog.records)


def test_the_clients_are_closed_even_when_the_app_stops_after_a_failure() -> None:
    closed: list[str] = []
    app = FastAPI(lifespan=build_lifespan([lambda: closed.append("a")]))

    with pytest.raises(RuntimeError), TestClient(app):
        raise RuntimeError("stop")

    assert closed == ["a"]


# --- 実際のプロセス ---


def run_api(**values: str) -> subprocess.CompletedProcess[str]:
    all_values = {**REQUIRED_ENVIRONMENT, **values}
    environment = {f"LORELEY_API_{name.upper()}": value for name, value in all_values.items()}
    environment["PYTHONPATH"] = str(SOURCE_DIRECTORY)  # インストールされていなくても import できる
    # `PATH` などは渡さない(実行環境の `LORELEY_API_*` が混ざらないようにするため)。
    # `timeout` を超えると `run` が子プロセスを kill する(ハングしても、テストは止まる)。
    return subprocess.run(
        [sys.executable, "-m", "loreley_api.main"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_the_process_with_an_invalid_port_fails_without_showing_the_value() -> None:
    result = run_api(port=SENTINEL_PORT)

    assert result.returncode != 0
    assert "invalid settings: port: int_parsing" in result.stderr
    assert SENTINEL_PORT not in result.stdout + result.stderr
    assert result.stderr.strip().splitlines()[-1].startswith("loreley_api.config.ConfigError")


def test_the_process_without_the_required_settings_fails_without_showing_values() -> None:
    environment = {"PYTHONPATH": str(SOURCE_DIRECTORY), "LORELEY_API_CRAWLER_URL": "ftp://SENTINEL"}
    result = subprocess.run(
        [sys.executable, "-m", "loreley_api.main"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode != 0
    assert "opensearch_url: missing" in result.stderr
    assert "crawler_url: url_scheme" in result.stderr
    assert "SENTINEL" not in result.stdout + result.stderr
