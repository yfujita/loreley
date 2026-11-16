"""`main` のテストの共通部品。

`main` の本物の組み立て(`assemble`・`start_components`・`stop_components`・`main`)を、メモリ上の
Repository・fake の Indexer で動かす。実 OpenSearch・実 Indexer は使わない。外部への入り口
(`create_backends`・`uvicorn.run`)だけを差し替える。スレッドの待ちには必ず上限を付ける。
"""

import functools
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest

from loreley_crawler import main as main_module
from loreley_crawler.config import CrawlerConfig, Settings, build_config
from loreley_crawler.connectors.registry import ConnectorRegistry
from loreley_crawler.main import Backends, Components, assemble
from tests.crawl.support import RecordingIndexerClient
from tests.fakes.clock import FixedClock
from tests.fakes.fake_connector import FakeConnectorType
from tests.fakes.in_memory_repository import InMemoryRepository
from tests.main.conftest import PREFIX

OWNER = "crawler-1"
OPENSEARCH_PASSWORD = "SENTINEL-opensearch-password"
CONFIG_SECRET = "SENTINEL-connector-config-secret"
DOCUMENT_SENTINEL = "SENTINEL-document-content"
WAIT_TIMEOUT_SECONDS = 10.0

# 待たずにリトライする(接続失敗のテストが長引かないように)。
NO_BACKOFF = {
    "RETRY_INITIAL_BACKOFF_SECONDS": "0",
    "RETRY_MAX_BACKOFF_SECONDS": "0",
}
REQUIRED = {
    "OWNER": OWNER,
    "OPENSEARCH_URL": "http://opensearch:9200",
    "INDEXER_URL": "http://indexer:8000",
}


def set_env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for name, value in {**REQUIRED, **NO_BACKOFF, **values}.items():
        monkeypatch.setenv(PREFIX + name.upper(), value)


def make_config(**overrides: Any) -> CrawlerConfig:
    values: dict[str, Any] = {
        "owner": OWNER,
        "opensearch_url": "http://opensearch:9200",
        "indexer_url": "http://indexer:8000",
        "retry_initial_backoff_seconds": 0.0,
        "retry_max_backoff_seconds": 0.0,
        **overrides,
    }
    return build_config(Settings(**values))


@dataclass
class Fakes:
    """`Backends` の中身。ハートビート専用の Repository は、既定では `jobs` と同じインスタンス。"""

    sources: InMemoryRepository = field(default_factory=InMemoryRepository)
    jobs: InMemoryRepository = field(default_factory=InMemoryRepository)
    indexer: RecordingIndexerClient = field(default_factory=RecordingIndexerClient)
    heartbeat_jobs: InMemoryRepository | None = None

    @property
    def backends(self) -> Backends:
        return Backends(
            sources_repository=self.sources,
            jobs_repository=self.jobs,
            heartbeat_jobs_repository=self.heartbeat_jobs or self.jobs,
            indexer_client=self.indexer,
        )


def make_components(
    fakes: Fakes | None = None,
    *,
    config: CrawlerConfig | None = None,
    clock: FixedClock | None = None,
    connector_type: FakeConnectorType | None = None,
) -> tuple[Components, Fakes]:
    fakes = fakes or Fakes()
    registry = (
        ConnectorRegistry({"file_system": connector_type}) if connector_type is not None else None
    )
    components = assemble(
        config or make_config(),
        fakes.backends,
        clock=clock or FixedClock(),
        connector_registry=registry,
    )
    return components, fakes


def record_calls(
    monkeypatch: pytest.MonkeyPatch, target: Any, name: str, events: list[str], label: str
) -> None:
    """`target.name` を、呼び出しを `events` に記録してから元の関数を呼ぶものに替える。"""
    original = getattr(target, name)

    @functools.wraps(original)
    def recorded(*args: Any, **kwargs: Any) -> Any:
        events.append(label)
        return original(*args, **kwargs)

    monkeypatch.setattr(target, name, recorded)


def record_startup(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    """起動順に関わる呼び出しを、`events` に記録する。"""
    for name in ("load_config", "configure_logging", "warn_about_unchecked_indexer_limits"):
        record_calls(monkeypatch, main_module, name, events, name)
    record_calls(monkeypatch, main_module, "assemble", events, "assemble")
    record_calls(monkeypatch, main_module, "create_app", events, "create_app")
    record_calls(monkeypatch, main_module.StartupRecovery, "run", events, "recovery.run")
    record_calls(monkeypatch, main_module.JobRunner, "start", events, "runner.start")
    record_calls(monkeypatch, main_module.Scheduler, "start", events, "scheduler.start")
    record_calls(monkeypatch, main_module.Scheduler, "request_stop", events, "scheduler.stop")
    record_calls(monkeypatch, main_module.JobRunner, "request_stop", events, "runner.stop")


def install_backends(
    monkeypatch: pytest.MonkeyPatch, fakes: Fakes, events: list[str] | None = None
) -> None:
    def create_backends(config: CrawlerConfig) -> Backends:
        if events is not None:
            events.append("create_backends")
        return fakes.backends

    monkeypatch.setattr(main_module, "create_backends", create_backends)


def install_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    serve: Callable[[Any], None] | None = None,
) -> dict[str, Any]:
    """`uvicorn.run` を、HTTP を開かず、渡された引数を記録する関数に替える(`serve` は、
    開いている間に行うこと。SIGTERM で戻る代わりに、`serve` が戻ると停止する)。"""
    captured: dict[str, Any] = {}

    def run(app: Any, **kwargs: Any) -> None:
        events.append("uvicorn.run")
        captured.update(kwargs, app=app)
        if serve is not None:
            serve(app)

    monkeypatch.setattr(main_module.uvicorn, "run", run)
    return captured


def started_threads() -> set[str]:
    return {thread.name for thread in threading.enumerate()}
