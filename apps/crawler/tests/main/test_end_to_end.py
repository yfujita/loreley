"""`main()` 経由の一気通貫: 起動 → API 呼び出し → ジョブ実行 → 停止(完了条件 3・8)。

fake の Indexer・メモリ上の Repository・本物の FS Connector(一時ディレクトリ)で、`main()` の本物の
組み立て・起動順・停止順を動かす。`uvicorn.run` の代わりに、開いている間の API 呼び出しを行う。
待ちはスリープに頼らず、Job Runner がロックを解放する直前に立つ `Event` を待つ。
"""

import logging
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from loreley_crawler import main as main_module
from loreley_crawler.config import ConfigError
from tests.fakes import in_memory_repository as ops
from tests.main.support import (
    CONFIG_SECRET,
    DOCUMENT_SENTINEL,
    OPENSEARCH_PASSWORD,
    WAIT_TIMEOUT_SECONDS,
    Fakes,
    install_backends,
    install_uvicorn,
    set_env,
    started_threads,
)

SENTINELS = (CONFIG_SECRET, DOCUMENT_SENTINEL, OPENSEARCH_PASSWORD)


class Scenario:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "docs"
        self.root.mkdir()
        (self.root / "a.txt").write_text(f"hello {DOCUMENT_SENTINEL}", encoding="utf-8")
        (self.root / "b.md").write_text(f"# title {DOCUMENT_SENTINEL}", encoding="utf-8")
        self.responses: dict[str, Any] = {}
        self.lock_released = threading.Event()

    def serve(self, app: Any) -> None:
        """HTTP が開いている間に行うこと。ジョブがロックを解放する直前まで待つ。"""
        client = TestClient(app, raise_server_exceptions=False)
        body = {
            "source_id": "docs",
            "connector_type": "file_system",
            "connector_config": {"root": str(self.root)},
            "ttl": 2_592_000,
            "ratio_threshold": 0.3,
            "min_delete_count": 10,
        }
        self.responses["healthz"] = client.get("/healthz")
        # 秘密を含む設定は、Connector が `config_invalid` で拒否する(説明文に値は出ない)。
        rejected = {**body, "connector_config": {**body["connector_config"], "x": CONFIG_SECRET}}
        self.responses["rejected"] = client.post("/sources", json=rejected)
        self.responses["register"] = client.post("/sources", json=body)
        self.responses["crawl"] = client.post("/sources/docs/crawl-jobs")
        assert self.lock_released.wait(WAIT_TIMEOUT_SECONDS), "the job did not finish"


def run_scenario(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **env: str
) -> tuple[Scenario, Fakes]:
    scenario = Scenario(tmp_path)
    fakes = Fakes()
    fakes.jobs.behavior.before(ops.DELETE, scenario.lock_released.set, key="lock-docs")
    set_env(
        monkeypatch,
        log_level="DEBUG",
        opensearch_username="crawler",
        opensearch_password=OPENSEARCH_PASSWORD,
        **env,
    )
    install_backends(monkeypatch, fakes)
    install_uvicorn(monkeypatch, [], scenario.serve)
    main_module.main()
    return scenario, fakes


def test_a_source_is_registered_crawled_and_finished_through_main(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, restore_logging: None
) -> None:
    threads_before = started_threads()

    scenario, fakes = run_scenario(monkeypatch, tmp_path)

    responses = scenario.responses
    assert responses["healthz"].status_code == 200
    assert responses["rejected"].status_code == 400
    assert responses["rejected"].json()["error"]["code"] == "config_invalid"
    assert responses["register"].status_code == 201
    crawl = responses["crawl"]
    assert crawl.status_code == 202
    job_id = crawl.json()["job_id"]

    job = fakes.jobs.body_of(job_id)
    assert job is not None
    assert job["status"] == "succeeded"
    assert job["registration"]["enumerated_count"] == 2
    assert job["registration"]["partial"] is False
    assert fakes.jobs.body_of("lock-docs") is None  # 正常終了は、ロックを解放する
    events = fakes.indexer.events
    assert events[0] == "start" and events[1].startswith("last_seen:")
    registered = ",".join(event for event in events if event.startswith("register:"))
    assert "a.txt" in registered and "b.md" in registered
    assert events[-2:] == ["finish:enumeration_completed", "status"]
    # 停止処理を終えて、スレッドが残っていない。
    assert not {"job-runner", "scheduler"} & (started_threads() - threads_before)


def test_no_log_or_response_contains_a_secret_a_config_value_or_a_document_body(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    restore_logging: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scenario, _ = run_scenario(monkeypatch, tmp_path)

    captured = capsys.readouterr()
    logs = captured.err + captured.out
    assert "starting the HTTP server" in logs  # ログが取れている(空の検査にしない)
    for sentinel in SENTINELS:
        assert sentinel not in logs, sentinel
    for name, response in scenario.responses.items():
        if name != "register":  # 登録の 201 は、保存した設定をそのまま返す契約
            for sentinel in SENTINELS:
                assert sentinel not in response.text, (name, sentinel)


def test_a_config_error_message_never_contains_the_password(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    set_env(
        monkeypatch,
        opensearch_username="crawler",
        opensearch_password=OPENSEARCH_PASSWORD,
        heartbeat_stop_timeout_seconds="1",
    )
    monkeypatch.delenv("LORELEY_CRAWLER_OWNER")

    with pytest.raises(ConfigError) as raised:
        main_module.main()

    assert OPENSEARCH_PASSWORD not in f"{raised.value} {raised.value!r}"


def test_main_wires_the_password_into_the_log_masking(
    monkeypatch: pytest.MonkeyPatch,
    restore_logging: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """設定から分かっている秘密値は、うっかりログに渡されても伏せられる(`secrets=config.log_secrets`)。"""
    set_env(monkeypatch, opensearch_username="crawler", opensearch_password=OPENSEARCH_PASSWORD)
    install_backends(monkeypatch, Fakes())
    install_uvicorn(
        monkeypatch,
        [],
        lambda app: logging.getLogger("leaky").warning("password=%s", OPENSEARCH_PASSWORD),
    )

    main_module.main()

    stderr = capsys.readouterr().err
    assert "password=***" in stderr
    assert OPENSEARCH_PASSWORD not in stderr
