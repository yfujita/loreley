"""起動順・停止・組み立て(module 5.6、arch 12章、完了条件 9)。

起動順: 設定 → 窓口(クライアント 2 つ)→ 組み立て → 起動時の整理 → 削除ワーカー → 要約ワーカー
→ HTTP の受け付け(`/healthz` が 200)。停止は逆順。
"""

import threading
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import loreley_indexer.main as main_module
from loreley_indexer.crawl_runs import CrawlRuns, DeletionManager
from loreley_indexer.crawl_runs.lifecycle import DeletionReason, DeletionStatus
from loreley_indexer.documents import Summarization
from loreley_indexer.infrastructure.llm import DisabledLlmClient
from loreley_indexer.infrastructure.opensearch import OpenSearchUnavailableError
from loreley_indexer.main import Backends, StartupError, build_application, create_backends
from tests.api.factories import START_PATH, make_settings, start_json
from tests.crawl_runs.deletion.scenario import (
    EXPIRED_AT,
    SEEN_AT,
    ids,
    queued_result,
    remaining,
    seed_documents,
)
from tests.crawl_runs.factories import CRAWL_ID, stored_result
from tests.documents.summarization.conftest import seed_pending
from tests.fakes import in_memory_store as store_ops
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore
from tests.fakes.llm import FakeLlmClient
from tests.fakes.waiting import wait_until

WAIT_SECONDS = 5.0


@pytest.fixture
def backends(
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    llm: FakeLlmClient,
) -> Backends:
    return Backends(
        search_index=search_index, deletions_store=deletions_store, jobs_store=jobs_store, llm=llm
    )


WORKER_THREAD_PREFIXES = ("deletion-worker", "summary-worker")


@pytest.fixture
def worker_threads() -> Callable[[], list[str]]:
    """このテストの中で起動されたワーカーのスレッド名。

    ほかのテストが残したスレッド(止め忘れ・停止待ちの途中)に巻き込まれないよう、
    テストの開始時点に存在したスレッドは除く。
    """
    existing = set(threading.enumerate())

    def current() -> list[str]:
        return sorted(
            thread.name
            for thread in threading.enumerate()
            if thread not in existing and thread.name.startswith(WORKER_THREAD_PREFIXES)
        )

    return current


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """起動の各段階が呼ばれた順の記録。"""
    recorded: list[str] = []

    def record_calls(owner: type, name: str, label: str) -> None:
        original = getattr(owner, name)

        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            recorded.append(label)
            return original(self, *args, **kwargs)

        monkeypatch.setattr(owner, name, wrapper)

    record_calls(CrawlRuns, "fail_unfinished_crawls_after_restart", "cleanup")
    record_calls(DeletionManager, "start", "deletion.start")
    record_calls(DeletionManager, "stop", "deletion.stop")
    record_calls(Summarization, "start", "summarization.start")
    record_calls(Summarization, "stop", "summarization.stop")
    return recorded


# --- 起動順(完了条件 9) ---


def test_the_cleanup_runs_before_the_workers_and_the_workers_stop_in_reverse_order(
    backends: Backends, events: list[str], clock: FixedClock
) -> None:
    app = build_application(make_settings(), backends, clock=clock)
    assert events == []  # 組み立てだけでは何も起動しない

    with TestClient(app) as client:
        assert events == ["cleanup", "deletion.start", "summarization.start"]
        assert client.get("/healthz").status_code == 200

    assert events[3:] == ["summarization.stop", "deletion.stop"]


def test_requests_are_not_handled_until_the_cleanup_has_completed(
    backends: Backends,
    deletions_store: InMemoryStore,
    clock: FixedClock,
    events: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """起動時の整理の途中は、どの API も `/healthz` も処理されない(503)。完了後に 200 になる。"""
    cleanup_started = threading.Event()
    release_cleanup = threading.Event()
    original = CrawlRuns.fail_unfinished_crawls_after_restart

    def slow_cleanup(self: CrawlRuns) -> int:
        cleanup_started.set()
        assert release_cleanup.wait(WAIT_SECONDS)
        return original(self)

    monkeypatch.setattr(CrawlRuns, "fail_unfinished_crawls_after_restart", slow_cleanup)
    app = build_application(make_settings(), backends, clock=clock)
    started = threading.Event()
    stop = threading.Event()

    def run_server() -> None:
        with TestClient(app):  # lifespan が動く(起動が整理で止まる)
            started.set()
            stop.wait(WAIT_SECONDS)

    thread = threading.Thread(target=run_server)
    thread.start()
    try:
        assert cleanup_started.wait(WAIT_SECONDS)
        probe = TestClient(app)  # `with` を使わない(lifespan は動かさず、リクエストだけを送る)
        during_cleanup = [
            probe.get("/healthz"),
            probe.post(START_PATH, json=start_json()),
            probe.get(f"/crawls/{CRAWL_ID}"),
        ]
        assert [response.status_code for response in during_cleanup] == [503, 503, 503]
        assert deletions_store.record_ids() == []  # リクエストは処理されていない
        assert "deletion.start" not in events  # ワーカーも始まっていない

        release_cleanup.set()
        assert started.wait(WAIT_SECONDS)
        assert probe.get("/healthz").status_code == 200
    finally:
        release_cleanup.set()
        stop.set()
        thread.join(WAIT_SECONDS)


def test_a_deletion_accepted_before_the_restart_is_failed_and_not_resumed(
    backends: Backends,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-93: 整理が先。先に始めると、再起動前に受理した削除を再開して文書を消してしまう。"""
    expired = ids(2_000, 3)
    seed_documents(search_index, expired, last_seen_at=EXPIRED_AT)
    seed_documents(search_index, ids(1_000, 2), last_seen_at=SEEN_AT)
    waiting = queued_result(enumerated_count=2)
    deletions_store.seed(f"deletion_result-{CRAWL_ID}", waiting.to_body())
    status_when_the_worker_starts: list[DeletionStatus] = []
    original_start = DeletionManager.start

    def spying_start(self: Any) -> None:
        status_when_the_worker_starts.append(stored_result(deletions_store).status)
        original_start(self)

    monkeypatch.setattr(DeletionManager, "start", spying_start)
    app = build_application(make_settings(), backends, clock=clock)

    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        # ワーカーに十分な時間(複数回の走査と起床)を与えても、削除されない。
        client.post("/crawls/start", json=start_json(crawl_id="job-next"))
        time.sleep(0.2)

    assert status_when_the_worker_starts == [DeletionStatus.FAILED]
    result = stored_result(deletions_store)
    assert (result.status, result.reason) == (DeletionStatus.FAILED, DeletionReason.INDEXER_RESTART)
    assert remaining(search_index, expired) == set(expired)


def test_the_cleanup_runs_exactly_once_per_start(
    backends: Backends, events: list[str], clock: FixedClock
) -> None:
    app = build_application(make_settings(), backends, clock=clock)

    with TestClient(app) as client:
        client.get("/healthz")
        client.get("/healthz")

    assert events.count("cleanup") == 1


def test_the_workers_are_stopped_after_the_server_stops(
    backends: Backends, clock: FixedClock, worker_threads: Callable[[], list[str]]
) -> None:
    app = build_application(make_settings(summary_enabled=True), backends, clock=clock)
    assert worker_threads() == []

    with TestClient(app):
        assert worker_threads() == ["deletion-worker", "summary-worker-0"]

    assert worker_threads() == []


def test_a_failure_to_start_the_summary_worker_stops_the_deletion_worker(
    backends: Backends,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    worker_threads: Callable[[], list[str]],
) -> None:
    def failing_start(self: Summarization) -> None:
        raise RuntimeError("cannot start")

    monkeypatch.setattr(Summarization, "start", failing_start)
    app = build_application(make_settings(), backends, clock=clock)

    with pytest.raises(RuntimeError), TestClient(app):
        pass

    assert worker_threads() == []


def test_a_failure_after_the_first_summary_worker_has_started_still_stops_the_summarization(
    backends: Backends,
    clock: FixedClock,
    events: list[str],
    monkeypatch: pytest.MonkeyPatch,
    worker_threads: Callable[[], list[str]],
) -> None:
    """`start()` が途中(1 本目のスレッドを起動した後)で失敗しても、`stop()` で起動済みを止める。"""

    def start_then_fail(self: Summarization) -> None:
        self.workers.start()
        assert worker_threads() == ["deletion-worker", "summary-worker-0"]
        raise RuntimeError("failed after the first thread")

    monkeypatch.setattr(Summarization, "start", start_then_fail)
    app = build_application(make_settings(summary_enabled=True), backends, clock=clock)

    with pytest.raises(RuntimeError, match="failed after the first thread"), TestClient(app):
        pass

    assert events == ["cleanup", "deletion.start", "summarization.stop", "deletion.stop"]
    assert worker_threads() == []


def test_a_failure_of_the_cleanup_keeps_the_application_from_starting(
    backends: Backends,
    deletions_store: InMemoryStore,
    clock: FixedClock,
    worker_threads: Callable[[], list[str]],
) -> None:
    deletions_store.behavior.inject(
        store_ops.LIST, OpenSearchUnavailableError("http_503"), times=None
    )
    app = build_application(make_settings(), backends, clock=clock)

    with pytest.raises(OpenSearchUnavailableError), TestClient(app):
        pass

    assert worker_threads() == []  # ワーカーは始まらない


# --- 受け付けの開始と停止(`ready`) ---


def healthz_status_of(app: FastAPI) -> int:
    """`with` を使わないクライアント(lifespan は動かさない)で、いまの受け付けの状態を調べる。"""
    return TestClient(app).get("/healthz").status_code


def test_requests_are_not_accepted_while_the_workers_start_but_are_after_all_have_started(
    backends: Backends, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """受け付けの開始は、整理と 2 つのワーカーの起動の後(module 5.6)。起動の途中は 503。"""
    app = build_application(make_settings(), backends, clock=clock)
    statuses_during_start: dict[str, int] = {}

    def record_status_during(owner: type, label: str) -> None:
        original = owner.start  # type: ignore[attr-defined]

        def wrapper(self: Any) -> Any:
            statuses_during_start[label] = healthz_status_of(app)
            return original(self)

        monkeypatch.setattr(owner, "start", wrapper)

    record_status_during(DeletionManager, "deletion.start")
    record_status_during(Summarization, "summarization.start")

    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200

    assert statuses_during_start == {"deletion.start": 503, "summarization.start": 503}


def test_requests_are_not_accepted_any_more_once_the_shutdown_has_begun(
    backends: Backends, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """停止の最初に受け付けを止める(ワーカーを止めている間に、新しい処理を始めさせない)。"""
    app = build_application(make_settings(), backends, clock=clock)
    statuses_during_stop: dict[str, int] = {}

    def record_status_during(owner: type, label: str) -> None:
        original = owner.stop  # type: ignore[attr-defined]

        def wrapper(self: Any) -> Any:
            statuses_during_stop[label] = healthz_status_of(app)
            return original(self)

        monkeypatch.setattr(owner, "stop", wrapper)

    record_status_during(Summarization, "summarization.stop")
    record_status_during(DeletionManager, "deletion.stop")

    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200

    assert statuses_during_stop == {"summarization.stop": 503, "deletion.stop": 503}
    assert healthz_status_of(app) == 503  # 停止後も立っていない


# --- 停止(ある停止が失敗しても、残りを行う) ---


@pytest.fixture
def closed_connections() -> list[str]:
    return []


@pytest.fixture
def backends_that_record_closing(
    backends: Backends, events: list[str], closed_connections: list[str]
) -> Backends:
    def close() -> None:
        events.append("close_connections")
        closed_connections.append("closed")

    return replace(backends, close_connections=close)


def test_the_connections_are_closed_last_after_the_workers_have_stopped(
    backends_that_record_closing: Backends, events: list[str], clock: FixedClock
) -> None:
    app = build_application(make_settings(), backends_that_record_closing, clock=clock)

    with TestClient(app):
        assert "close_connections" not in events

    assert events[-3:] == ["summarization.stop", "deletion.stop", "close_connections"]


def test_a_failure_to_stop_the_summarization_does_not_skip_the_rest_of_the_shutdown(
    backends_that_record_closing: Backends,
    events: list[str],
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    worker_threads: Callable[[], list[str]],
    closed_connections: list[str],
) -> None:
    def failing_stop(self: Summarization) -> None:
        events.append("summarization.stop")
        raise RuntimeError("cannot stop")

    monkeypatch.setattr(Summarization, "stop", failing_stop)
    app = build_application(make_settings(), backends_that_record_closing, clock=clock)

    with pytest.raises(RuntimeError, match="cannot stop"), TestClient(app):
        assert worker_threads() == ["deletion-worker"]

    assert events[-3:] == ["summarization.stop", "deletion.stop", "close_connections"]
    assert worker_threads() == []
    assert closed_connections == ["closed"]
    assert healthz_status_of(app) == 503


def test_the_connections_are_closed_even_when_the_startup_fails(
    backends_that_record_closing: Backends,
    deletions_store: InMemoryStore,
    clock: FixedClock,
    closed_connections: list[str],
) -> None:
    deletions_store.behavior.inject(
        store_ops.LIST, OpenSearchUnavailableError("http_503"), times=None
    )
    app = build_application(make_settings(), backends_that_record_closing, clock=clock)

    with pytest.raises(OpenSearchUnavailableError), TestClient(app):
        pass

    assert closed_connections == ["closed"]


# --- 要約(要件: 有効かつプロバイダ未設定なら起動失敗) ---


def test_summarization_enabled_without_a_provider_fails_the_startup(
    search_index: InMemorySearchIndex, deletions_store: InMemoryStore, jobs_store: InMemoryStore
) -> None:
    backends = Backends(
        search_index=search_index,
        deletions_store=deletions_store,
        jobs_store=jobs_store,
        llm=DisabledLlmClient(),
    )

    with pytest.raises(StartupError, match="no LLM provider is configured"):
        build_application(make_settings(summary_enabled=True), backends)


def test_summarization_disabled_starts_without_a_provider(
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    clock: FixedClock,
    worker_threads: Callable[[], list[str]],
) -> None:
    backends = Backends(
        search_index=search_index,
        deletions_store=deletions_store,
        jobs_store=jobs_store,
        llm=DisabledLlmClient(),
    )

    app = build_application(make_settings(summary_enabled=False), backends, clock=clock)

    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert [name for name in worker_threads() if name.startswith("summary")] == []


def test_the_default_backends_have_no_provider_so_enabling_summarization_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """具体的なプロバイダは未実装。既定の窓口では、要約を有効にすると起動に失敗する。"""
    settings = make_settings(summary_enabled=True)

    with pytest.raises(StartupError):
        build_application(settings, create_backends(settings))


def test_the_startup_error_message_has_no_setting_values() -> None:
    settings = make_settings(summary_enabled=True, opensearch_password="SENTINEL-PASSWORD")

    with pytest.raises(StartupError) as error_info:
        build_application(settings, create_backends(settings))

    assert "SENTINEL-PASSWORD" not in str(error_info.value)


def test_the_started_summarization_rescans_pending_documents_at_startup(
    backends: Backends,
    search_index: InMemorySearchIndex,
    clock: FixedClock,
) -> None:
    """再起動前に `pending` のまま残った文書が、起動時の再走査で要約される(受け付けと並行)。"""
    seed_pending(search_index, "doc-1")
    app = build_application(make_settings(summary_enabled=True), backends, clock=clock)

    with TestClient(app):
        assert wait_until(lambda: search_index.source_of("doc-1")["summary_status"] == "generated")


# --- 組み立て ---


def test_the_finish_notification_wakes_the_deletion_worker_through_the_shared_event(
    backends: Backends,
    search_index: InMemorySearchIndex,
    clock: FixedClock,
) -> None:
    """`CrawlRuns` の `wake` と削除ワーカーが、同じイベントでつながっている(間隔は 30 秒)。"""
    seen, expired = ids(1_000, 2), ids(2_000, 2)
    seed_documents(search_index, seen, last_seen_at=SEEN_AT)
    seed_documents(search_index, expired, last_seen_at=EXPIRED_AT)
    app = build_application(make_settings(), backends, clock=clock)

    with TestClient(app) as client:
        client.post(START_PATH, json=start_json(ttl=3 * 86_400))
        client.post(
            f"/crawls/{CRAWL_ID}/finish",
            json={
                "source_id": "src-docs",
                "outcome": "enumeration_completed",
                "enumerated_count": 2,
                "skipped_document_ids": [],
                "oversize_document_ids": [],
                "finished_at": "2026-11-09T01:12:30Z",
            },
        )

        assert wait_until(lambda: client.get(f"/crawls/{CRAWL_ID}").json()["status"] == "deleted")

    assert remaining(search_index, expired) == set()


def test_the_registration_and_last_seen_share_one_source_lock(
    backends: Backends, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同じソースの登録と `last-seen` は、同じロックで直列化される(案 19)。"""
    locks: dict[str, Any] = {}

    def recording(name: str, original: type) -> type:
        class Recording(original):  # type: ignore[valid-type, misc]
            def __init__(self, **kwargs: Any) -> None:
                locks[name] = kwargs["source_locks"]
                super().__init__(**kwargs)

        return Recording

    monkeypatch.setattr(
        main_module, "DocumentRegistrar", recording("registrar", main_module.DocumentRegistrar)
    )
    monkeypatch.setattr(
        main_module, "LastSeenUpdater", recording("last_seen", main_module.LastSeenUpdater)
    )

    build_application(make_settings(), backends, clock=clock)

    assert locks["registrar"] is locks["last_seen"]


# --- create_backends: クライアントは 2 つ ---


def test_create_backends_builds_a_normal_client_and_a_delete_by_query_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: dict[str, list[Any]] = {"normal": [], "delete_by_query": []}
    adapter_arguments: dict[str, Any] = {}
    normal_client, delete_by_query_client = object(), object()

    def create_normal(config: Any) -> object:
        created["normal"].append(config)
        return normal_client

    def create_delete_by_query(config: Any) -> object:
        created["delete_by_query"].append(config)
        return delete_by_query_client

    class RecordingAdapter:
        def __init__(self, client: Any, index_name: str, **kwargs: Any) -> None:
            adapter_arguments.update(client=client, index_name=index_name, **kwargs)

    class RecordingStore:
        def __init__(self, client: Any, index_name: str) -> None:
            self.client, self.index_name = client, index_name

    monkeypatch.setattr(main_module, "create_opensearch_client", create_normal)
    monkeypatch.setattr(main_module, "create_delete_by_query_client", create_delete_by_query)
    monkeypatch.setattr(main_module, "OpenSearchSearchIndexRepository", RecordingAdapter)
    monkeypatch.setattr(main_module, "OpenSearchStore", RecordingStore)
    settings = make_settings(
        os_delete_by_query_timeout_seconds=900,
        update_retry_on_conflict=4,
        search_index_name="docs-x",
        deletions_index_name="deletions-x",
        jobs_index_name="jobs-x",
    )

    backends = create_backends(settings)

    assert len(created["normal"]) == len(created["delete_by_query"]) == 1
    assert created["normal"][0] == settings.opensearch_connection()
    assert adapter_arguments == {
        "client": normal_client,
        "index_name": "docs-x",
        "update_retry_on_conflict": 4,
        "delete_by_query_client": delete_by_query_client,
        "delete_by_query_timeout_seconds": 900,
    }
    assert (backends.deletions_store.index_name, backends.jobs_store.index_name) == (
        "deletions-x",
        "jobs-x",
    )
    assert backends.deletions_store.client is backends.jobs_store.client is normal_client
    assert isinstance(backends.llm, DisabledLlmClient)


def test_create_backends_closes_both_clients_even_if_one_fails_to_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normal_client, delete_by_query_client = MagicMock(), MagicMock()
    normal_client.close.side_effect = RuntimeError("cannot close")
    monkeypatch.setattr(main_module, "create_opensearch_client", lambda config: normal_client)
    monkeypatch.setattr(
        main_module, "create_delete_by_query_client", lambda config: delete_by_query_client
    )

    backends = create_backends(make_settings())
    with pytest.raises(RuntimeError, match="cannot close"):
        backends.close_connections()

    normal_client.close.assert_called_once_with()
    delete_by_query_client.close.assert_called_once_with()


def test_create_backends_with_real_clients_makes_two_distinct_clients_without_connecting(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")
    settings = make_settings(opensearch_username="admin", opensearch_password="SENTINEL-PASSWORD")

    backends = create_backends(settings)

    try:
        search_index = backends.search_index
        assert search_index._client is not search_index._delete_by_query_client  # type: ignore[attr-defined]
        assert "SENTINEL-PASSWORD" not in caplog.text
        assert "SENTINEL-PASSWORD" not in repr(backends)
    finally:
        backends.close_connections()


# --- create_app: ログの設定 ---


def test_create_app_configures_the_logging_with_the_password_as_a_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        main_module, "configure_logging", lambda **kwargs: configured.append(kwargs)
    )
    settings = make_settings(opensearch_password="SENTINEL-PASSWORD", log_level="DEBUG")

    app = main_module.create_app(settings)

    assert isinstance(app, FastAPI)
    assert configured == [{"level": "DEBUG", "secrets": ["SENTINEL-PASSWORD"]}]


def test_create_app_without_a_password_passes_no_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    configured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        main_module, "configure_logging", lambda **kwargs: configured.append(kwargs)
    )

    main_module.create_app(make_settings())

    assert configured == [{"level": "INFO", "secrets": []}]


# --- main: uvicorn の起動方法 ---


def test_main_runs_a_single_process_without_uvicorns_access_log_and_logging_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LORELEY_INDEXER_OPENSEARCH_URL", "http://opensearch:9200")
    monkeypatch.setenv("LORELEY_INDEXER_HTTP_HOST", "0.0.0.0")
    monkeypatch.setenv("LORELEY_INDEXER_HTTP_PORT", "8123")
    app = object()
    monkeypatch.setattr(main_module, "create_app", lambda settings: app)
    runs: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(main_module.uvicorn, "run", lambda *a, **k: runs.append((a, k)))

    main_module.main()

    assert runs == [
        ((app,), {"host": "0.0.0.0", "port": 8123, "log_config": None, "access_log": False})
    ]
