import threading
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from loreley_indexer.documents.summarization import (
    SummarizationConfig,
    SummaryProcessor,
    SummaryRequestQueue,
    SummaryRescanner,
    SummaryWorkerPool,
)
from loreley_indexer.infrastructure.opensearch import StoreJobsReader
from tests.crawl_runs.factories import CRAWL_STARTED_AT_TEXT
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore
from tests.fakes.llm import FakeLlmClient

MAX_ATTEMPTS = 3
MAX_REREADS = 2
PAGE_SIZE = 2
MIN_RESCAN_INTERVAL_SECONDS = 60.0
MAX_RESCAN_INTERVAL_SECONDS = 600.0

BODY = "the body of the document"


@pytest.fixture
def config() -> SummarizationConfig:
    return SummarizationConfig(
        enabled=True,
        concurrency=1,
        max_attempts=MAX_ATTEMPTS,
        queue_size=10,
        rescan_page_size=PAGE_SIZE,
        rescan_min_interval_seconds=MIN_RESCAN_INTERVAL_SECONDS,
        rescan_max_interval_seconds=MAX_RESCAN_INTERVAL_SECONDS,
        write_conflict_max_rereads=MAX_REREADS,
        retry_backoff_initial_seconds=1.0,
        retry_backoff_factor=2.0,
        retry_backoff_max_seconds=3.0,
        input_max_chars=1000,
    )


@pytest.fixture
def disabled_config(config: SummarizationConfig) -> SummarizationConfig:
    return replace(config, enabled=False)


@pytest.fixture
def sleeps() -> list[float]:
    """バックオフの待ち時間の記録。実際には待たない。"""
    return []


@pytest.fixture
def make_processor(
    config: SummarizationConfig,
    search_index: InMemorySearchIndex,
    jobs_store: InMemoryStore,
    llm: FakeLlmClient,
    sleeps: list[float],
):
    def make(
        override: SummarizationConfig | None = None,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> SummaryProcessor:
        return SummaryProcessor(
            config=override if override is not None else config,
            search_index=search_index,
            jobs=StoreJobsReader(jobs_store),
            llm=llm,
            sleep=sleeps.append,
            should_stop=should_stop,
        )

    return make


@pytest.fixture
def processor(make_processor) -> SummaryProcessor:
    return make_processor()


@pytest.fixture
def rescanner(
    config: SummarizationConfig,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
    clock: FixedClock,
) -> SummaryRescanner:
    return SummaryRescanner(
        config=config, search_index=search_index, requests=summary_requests, clock=clock
    )


@pytest.fixture
def pool(
    config: SummarizationConfig,
    summary_requests: SummaryRequestQueue,
    processor: SummaryProcessor,
    rescanner: SummaryRescanner,
) -> SummaryWorkerPool:
    return SummaryWorkerPool(
        concurrency=config.concurrency,
        requests=summary_requests,
        processor=processor,
        rescanner=rescanner,
        stop_event=threading.Event(),
    )


class _SignalingCondition(threading.Condition):
    """`wait_for` に入ることを知らせる。

    知らせるのはロックを持ったまま行うので、テスト側の `submit()` や `close()` は、
    待ち手が実際に待ち状態に入る(ロックを手放す)まで、ロックを取れず進めない。
    """

    def __init__(self, waiting: threading.Event) -> None:
        super().__init__()
        self._waiting = waiting

    def wait_for[T](self, predicate: Callable[[], T], timeout: float | None = None) -> T:
        self._waiting.set()
        return super().wait_for(predicate, timeout)


def signal_when_a_taker_waits(queue: SummaryRequestQueue) -> threading.Event:
    """`queue.take(wait_seconds=...)` が待ち状態に入ったら立つイベントを返す。

    `SummaryRequestQueue` の内部名(`_condition`)に依存するのは、ここだけ。
    """
    waiting = threading.Event()
    queue._condition = _SignalingCondition(waiting)
    return waiting


def pending_source(document_id: str, **overrides: Any) -> dict[str, Any]:
    """要約が `pending` の登録済み文書(`search-index-v0.9.md` の項目)。"""
    base: dict[str, Any] = {
        "document_id": document_id,
        "source_id": "src-docs",
        "external_id": f"{document_id}.txt",
        "title": "Title",
        "mime_type": "text/plain",
        "size": 10,
        "source_updated_at": "2026-11-08T12:00:00.000Z",
        "content": BODY,
        "content_hash": "c" * 64,
        "text_hash": "t" * 64,
        "truncated": False,
        "index_status": "indexed",
        "summary_status": "pending",
        "indexed_at": "2026-11-09T01:00:00.000Z",
        "last_seen_at": CRAWL_STARTED_AT_TEXT,
    }
    return {**base, **overrides}


def seed_pending(
    search_index: InMemorySearchIndex, document_id: str = "doc-1", **overrides: Any
) -> str:
    search_index.seed(document_id, pending_source(document_id, **overrides))
    return document_id
