"""組み立て(`assemble`・`create_backends`)。

I/O もスレッドの開始もしないこと、共有する物が 1 つであること、Repository がちょうど 3 つで
ハートビートが専用のものを使うこと、`JobRunner` に両方の実行対象が渡ることを確かめる。
"""

from datetime import timedelta
from typing import Any

import pytest

from loreley_crawler import main as main_module
from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.crawl import CrawlExecutor
from loreley_crawler.jobs import JobType
from loreley_crawler.jobs.locks import LockStore
from loreley_crawler.jobs.locks.lock_document import new_lock_fields
from loreley_crawler.source_delete import SourceDeleteExecutor
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.in_memory_repository import InMemoryRepository
from tests.main.support import Fakes, make_components, make_config, started_threads

# --- 組み立てだけでは何も起きない ---


def test_assembling_starts_no_thread_and_touches_no_store_or_indexer() -> None:
    threads_before = started_threads()
    fakes = Fakes()

    make_components(fakes)

    assert started_threads() == threads_before
    for repository in (fakes.sources, fakes.jobs):
        assert repository.behavior.calls == []
    assert fakes.indexer.calls == []


# --- 共有と実行対象 ---


def test_the_job_runner_gets_both_executors() -> None:
    components, _ = make_components()

    executors: dict[JobType, Any] = components.runner._executors

    assert set(executors) == {JobType.CRAWL, JobType.SOURCE_DELETE}
    assert isinstance(executors[JobType.CRAWL], CrawlExecutor)
    assert isinstance(executors[JobType.SOURCE_DELETE], SourceDeleteExecutor)


def test_the_scheduler_and_the_api_share_one_job_admission() -> None:
    components, _ = make_components()

    assert components.scheduler._admission is components.api_dependencies.job_admission


def test_the_api_and_the_source_delete_share_one_source_store() -> None:
    components, _ = make_components()
    executors: dict[JobType, Any] = components.runner._executors

    delete_dependencies = executors[JobType.SOURCE_DELETE]._dependencies
    assert delete_dependencies.source_store is components.api_dependencies.source_store


def test_the_crawl_and_the_api_use_the_same_connector_registry() -> None:
    components, _ = make_components()
    executors: dict[JobType, Any] = components.runner._executors

    crawl_dependencies = executors[JobType.CRAWL]._dependencies
    assert crawl_dependencies.connector_registry is components.api_dependencies.connector_registry
    assert components.api_dependencies.connector_registry.registered_names == {"file_system"}


def test_the_crawl_executor_gets_the_configured_settings() -> None:
    config = make_config(chunk_size=7, max_raw_bytes=1_000_000, batch_max_raw_bytes=2_000_000)
    components, _ = make_components(config=config)
    executors: dict[JobType, Any] = components.runner._executors

    dependencies = executors[JobType.CRAWL]._dependencies
    assert dependencies.settings.chunk_size == 7
    assert dependencies.documents_settings.max_raw_bytes == 1_000_000


def test_the_jobs_settings_with_the_owner_reach_the_recovery_and_the_runner() -> None:
    components, _ = make_components(config=make_config(owner="crawler-77"))

    assert components.recovery._owner == "crawler-77"
    assert components.runner._owner == "crawler-77"


# --- ハートビートは専用の Repository ---


def test_the_heartbeat_writes_through_the_dedicated_repository_not_the_store_one() -> None:
    clock = FixedClock()
    fakes = Fakes(heartbeat_jobs=InMemoryRepository())
    components, _ = make_components(fakes, clock=clock)
    lock_body = new_lock_fields(
        source_id="docs", owner="crawler-1", job_id="job-1", acquired_at=DEFAULT_NOW
    )
    # 同じロック文書を、両方の Repository に置く(別のクライアントから同じ索引を見る状況を模す)。
    fakes.jobs.seed("lock-docs", lock_body)
    assert fakes.heartbeat_jobs is not None
    fakes.heartbeat_jobs.seed("lock-docs", lock_body)
    lock = LockStore(fakes.jobs, clock).read("docs")
    assert lock is not None
    heartbeat = components.heartbeat_factory()

    heartbeat.start(lock, DEFAULT_NOW + timedelta(seconds=300))
    try:
        heartbeat.tick()
    finally:
        assert heartbeat.stop() is True

    assert fakes.heartbeat_jobs.body_of("lock-docs")["lease_expires_at"] is not None
    assert fakes.jobs.body_of("lock-docs")["lease_expires_at"] is None
    assert fakes.jobs.write_calls() == []


def test_each_job_gets_its_own_heartbeat() -> None:
    components, _ = make_components()

    assert components.heartbeat_factory() is not components.heartbeat_factory()


# --- create_backends: Repository はちょうど 3 つ(R7) ---


class FakeClient:
    def __init__(self, name: str) -> None:
        self.name = name


def test_create_backends_makes_exactly_three_repositories_on_two_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(sources_index_name="s-index", jobs_index_name="j-index")
    created: list[tuple[str, str, Any]] = []
    store_client, heartbeat_client = FakeClient("store"), FakeClient("heartbeat")

    class RecordingRepository(InMemoryRepository):
        def __init__(self, client: FakeClient, index_name: str, settings: Any) -> None:
            super().__init__()
            created.append((client.name, index_name, settings))

    monkeypatch.setattr(main_module, "create_store_client", lambda c: store_client)
    monkeypatch.setattr(main_module, "create_heartbeat_client", lambda c: heartbeat_client)
    monkeypatch.setattr(main_module, "OpenSearchRepository", RecordingRepository)

    backends = main_module.create_backends(config)

    assert created == [
        ("store", "s-index", config.repository),
        ("store", "j-index", config.repository),
        ("heartbeat", "j-index", config.repository),
    ]
    assert backends.sources_repository is not backends.jobs_repository
    assert backends.heartbeat_jobs_repository is not backends.jobs_repository
    assert backends.indexer_client is not None


def test_each_client_is_created_from_its_own_timeout_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(
        os_store_request_timeout_seconds=12, os_heartbeat_request_timeout_seconds=3
    )
    timeouts: dict[str, float] = {}

    def create_store(connection: Any) -> FakeClient:
        timeouts["store"] = connection.store_request_timeout_seconds
        return FakeClient("store")

    def create_heartbeat(connection: Any) -> FakeClient:
        timeouts["heartbeat"] = connection.heartbeat_request_timeout_seconds
        return FakeClient("heartbeat")

    monkeypatch.setattr(main_module, "create_store_client", create_store)
    monkeypatch.setattr(main_module, "create_heartbeat_client", create_heartbeat)
    monkeypatch.setattr(main_module, "OpenSearchRepository", lambda *args: InMemoryRepository())

    main_module.create_backends(config)

    assert timeouts == {"store": 12, "heartbeat": 3}


def test_the_real_create_backends_only_builds_clients_and_does_not_connect() -> None:
    """実クライアントを作っても、最初の読み書きまで接続しない(接続の失敗は回復の段階で現れる)。"""
    backends = main_module.create_backends(make_config(opensearch_url="http://127.0.0.1:1"))

    assert backends.indexer_client is not None


def test_a_store_outage_surfaces_at_the_first_read_as_a_store_error() -> None:
    """閉じたポートへの接続は、リトライを尽くして `StoreUnavailableError` になる。"""
    config = make_config(opensearch_url="http://127.0.0.1:1")
    backends = main_module.create_backends(config)
    components = main_module.assemble(config, backends, clock=FixedClock())

    with pytest.raises(StoreUnavailableError):
        components.recovery.run()
