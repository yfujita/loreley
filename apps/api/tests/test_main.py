import logging
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from loreley_api.main import build_app, main

SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
SENTINEL_PORT = "SENTINEL-PORT"


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
    response = TestClient(build_app()).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_built_app_answers_an_unknown_path_with_a_json_404() -> None:
    response = TestClient(build_app()).get("/nope")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert response.json()["error"]["code"] == "not_found"


def test_building_and_running_the_app_makes_no_network_access(
    forbid_network_connections: None,
) -> None:
    """組み立てと、lifespan(開始・終了)の実行まで、外部に接続しない。"""
    with TestClient(build_app()) as client:
        assert client.get("/healthz").status_code == 200


def test_the_health_check_is_logged_at_debug_and_other_paths_at_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`debug_access_log_paths` の配線(`/healthz` は数秒おきに呼ばれるので DEBUG)。"""
    caplog.set_level(logging.DEBUG)
    client = TestClient(build_app())

    client.get("/healthz")
    client.get("/nope")

    levels = [
        (record.getMessage().split(" ")[1], record.levelno)
        for record in caplog.records
        if record.name == "loreley_api.access"
    ]
    assert levels == [("/healthz", logging.DEBUG), ("-", logging.INFO)]


# --- main()(uvicorn を差し替える。実際には起動しない) ---


def test_main_runs_uvicorn_once_with_the_settings_and_without_workers_or_reload(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
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


# --- 実際のプロセス ---


def run_api(**values: str) -> subprocess.CompletedProcess[str]:
    environment = {f"LORELEY_API_{name.upper()}": value for name, value in values.items()}
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
