import threading
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from loreley_indexer.crawl_runs import (
    CrawlRuns,
    DeletionConfig,
    DeletionManager,
    LifecycleConfig,
    create_deletion_manager,
)
from loreley_indexer.crawl_runs.lifecycle import DeletionResults
from loreley_indexer.infrastructure.opensearch import StoreJobsReader
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore

BATCH_SIZE = 3
PAGE_SIZE = 4
MAX_TARGETS = 50
RETRY_ATTEMPTS = 3
MAX_REREADS = 3
DISCARD_ATTEMPTS = 3
MAX_RERUNS = 2
RETENTION_COUNT = 20


@pytest.fixture
def deletion_config() -> DeletionConfig:
    return DeletionConfig(
        batch_size=BATCH_SIZE,
        max_deletion_targets=MAX_TARGETS,
        search_after_page_size=PAGE_SIZE,
        poll_interval_seconds=30.0,  # 走査ではなく起床通知で進むことを示すため、長くしておく
        poll_backoff_max_seconds=240.0,
        delete_error_retry_attempts=RETRY_ATTEMPTS,
        retry_backoff_initial_seconds=1.0,
        retry_backoff_factor=2.0,
        retry_backoff_max_seconds=30.0,
        write_conflict_max_rereads=MAX_REREADS,
        discard_max_attempts=DISCARD_ATTEMPTS,
        delete_by_query_max_reruns=MAX_RERUNS,
    )


@pytest.fixture
def jobs_reader(jobs_store: InMemoryStore) -> StoreJobsReader:
    return StoreJobsReader(jobs_store)


@pytest.fixture
def results(deletions_store: InMemoryStore, clock: FixedClock) -> DeletionResults:
    return DeletionResults(deletions_store, retention_count=RETENTION_COUNT, clock=clock)


@pytest.fixture
def sleeps() -> list[float]:
    """削除エラーの再試行の待ち時間の記録(スリープはしない)。"""
    return []


@pytest.fixture
def wake_event() -> threading.Event:
    return threading.Event()


@pytest.fixture
def make_manager(
    deletion_config: DeletionConfig,
    results: DeletionResults,
    search_index: InMemorySearchIndex,
    jobs_reader: StoreJobsReader,
    clock: FixedClock,
    sleeps: list[float],
    wake_event: threading.Event,
) -> Callable[..., DeletionManager]:
    """設定の一部を差し替えた削除の入口を作る(`sleep` の既定は、待ち時間を記録するだけ)。"""

    def make(**config_overrides: Any) -> DeletionManager:
        return create_deletion_manager(
            replace(deletion_config, **config_overrides),
            results=results,
            search_index=search_index,
            jobs=jobs_reader,
            clock=clock,
            wake_event=wake_event,
            jitter=lambda delay: delay,  # 待ち時間を決定的にする
            sleep=sleeps.append,
        )

    return make


@pytest.fixture
def manager(make_manager: Callable[..., DeletionManager]) -> DeletionManager:
    return make_manager()


@pytest.fixture
def crawl_runs(
    deletions_store: InMemoryStore, clock: FixedClock, wake_event: threading.Event
) -> CrawlRuns:
    """開始・終了通知の窓口。`wake` は削除ワーカーと同じイベント(本番の配線)。"""
    return CrawlRuns(
        config=LifecycleConfig(
            skip_oversize_id_limit=10,
            write_conflict_max_rereads=MAX_REREADS,
            deletion_retention_count=RETENTION_COUNT,
        ),
        deletions_store=deletions_store,
        clock=clock,
        wake=wake_event.set,
    )
