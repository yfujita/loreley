import pytest

from loreley_indexer.crawl_runs import CrawlRuns, LifecycleConfig
from loreley_indexer.crawl_runs.lifecycle import DeletionResults
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_store import InMemoryStore

ID_LIMIT = 5
MAX_REREADS = 3
RETENTION_COUNT = 3


@pytest.fixture
def lifecycle_config() -> LifecycleConfig:
    return LifecycleConfig(
        skip_oversize_id_limit=ID_LIMIT,
        write_conflict_max_rereads=MAX_REREADS,
        deletion_retention_count=RETENTION_COUNT,
    )


@pytest.fixture
def wakes() -> list[str]:
    """`wake` が呼ばれた回数の記録(削除ワーカーを起こす入口。案 2)。"""
    return []


@pytest.fixture
def crawl_runs(
    lifecycle_config: LifecycleConfig,
    deletions_store: InMemoryStore,
    clock: FixedClock,
    wakes: list[str],
) -> CrawlRuns:
    return CrawlRuns(
        config=lifecycle_config,
        deletions_store=deletions_store,
        clock=clock,
        wake=lambda: wakes.append("wake"),
    )


@pytest.fixture
def results(crawl_runs: CrawlRuns) -> DeletionResults:
    """ファサードが使う削除結果の窓口(P4 の deletion が同じインスタンスを使う)。"""
    return crawl_runs.results
