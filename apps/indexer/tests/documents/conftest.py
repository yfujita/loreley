from dataclasses import replace

import pytest

from loreley_indexer.common.source_locks import SourceLocks
from loreley_indexer.crawl_runs import AdmissionChecker
from loreley_indexer.documents import (
    DocumentRegistrar,
    LastSeenUpdater,
    RegistrationConfig,
)
from loreley_indexer.documents.extraction import ExtractionConfig, TextExtractor
from loreley_indexer.documents.summarization import SummaryRequestQueue
from loreley_indexer.infrastructure.opensearch import StoreJobsReader
from tests.crawl_runs.factories import make_result, seed_result
from tests.documents.factories import seed_lock
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore

MAX_RAW_BYTES = 1024
MAX_REREADS = 3
MAX_CONTENT_BYTES = 100


@pytest.fixture
def registration_config() -> RegistrationConfig:
    return RegistrationConfig(
        max_raw_bytes=MAX_RAW_BYTES,
        write_conflict_max_rereads=MAX_REREADS,
        max_last_seen_ids=5,
        summary_enabled=False,
    )


@pytest.fixture
def summary_requests() -> SummaryRequestQueue:
    return SummaryRequestQueue(max_size=10)


@pytest.fixture
def source_locks() -> SourceLocks:
    return SourceLocks()


@pytest.fixture
def jobs_reader(jobs_store: InMemoryStore) -> StoreJobsReader:
    return StoreJobsReader(jobs_store)


@pytest.fixture
def running_crawl(deletions_store: InMemoryStore, jobs_store: InMemoryStore) -> None:
    """開始通知を受理済み(`running`)で、Crawler がロックを持っている状態。"""
    seed_result(deletions_store, make_result())
    seed_lock(jobs_store)


@pytest.fixture
def make_registrar(
    registration_config: RegistrationConfig,
    deletions_store: InMemoryStore,
    search_index: InMemorySearchIndex,
    jobs_reader: StoreJobsReader,
    summary_requests: SummaryRequestQueue,
    source_locks: SourceLocks,
    clock: FixedClock,
):
    def make(
        config: RegistrationConfig | None = None,
        locks: SourceLocks | None = None,
        requests: SummaryRequestQueue | None = None,
    ) -> DocumentRegistrar:
        """`locks` を別にすると、別プロセスの Indexer のように並行する登録を再現できる。"""
        return DocumentRegistrar(
            config=config if config is not None else registration_config,
            admission_checker=AdmissionChecker(deletions_store),
            search_index=search_index,
            jobs=jobs_reader,
            extractor=TextExtractor(ExtractionConfig(max_content_bytes=MAX_CONTENT_BYTES)),
            summary_requests=requests if requests is not None else summary_requests,
            source_locks=locks if locks is not None else source_locks,
            clock=clock,
        )

    return make


@pytest.fixture
def registrar(make_registrar) -> DocumentRegistrar:
    return make_registrar()


@pytest.fixture
def summary_registrar(make_registrar, registration_config: RegistrationConfig) -> DocumentRegistrar:
    """要約が有効な登録(新しい本文は `pending` で書き、生成を依頼する)。"""
    return make_registrar(replace(registration_config, summary_enabled=True))


@pytest.fixture
def last_seen_updater(
    registration_config: RegistrationConfig,
    deletions_store: InMemoryStore,
    search_index: InMemorySearchIndex,
    jobs_reader: StoreJobsReader,
    source_locks: SourceLocks,
    clock: FixedClock,
) -> LastSeenUpdater:
    return LastSeenUpdater(
        config=registration_config,
        admission_checker=AdmissionChecker(deletions_store),
        search_index=search_index,
        jobs=jobs_reader,
        source_locks=source_locks,
        clock=clock,
    )
