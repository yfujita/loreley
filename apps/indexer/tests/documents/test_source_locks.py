"""登録と `last-seen` が同じ `SourceLocks` で直列化されること(arch 8章、plan 案19)。"""

import threading

import pytest

from loreley_indexer.crawl_runs import CrawlRuns, LifecycleConfig
from loreley_indexer.documents import DocumentRegistrar, LastSeenUpdater
from tests.crawl_runs.factories import make_start
from tests.documents.factories import id_of, make_context, make_document
from tests.fakes import in_memory_search_index as ops
from tests.fakes.clock import FixedClock
from tests.fakes.concurrency import BLOCKED_PROBE_SECONDS, JOIN_TIMEOUT_SECONDS
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore


@pytest.mark.usefixtures("running_crawl")
def test_last_seen_waits_for_a_registration_of_the_same_source(
    registrar: DocumentRegistrar,
    last_seen_updater: LastSeenUpdater,
    search_index: InMemorySearchIndex,
) -> None:
    """登録の処理の途中(PUT の直前)に `last-seen` が来ても、登録が終わるまで始まらない。"""
    document = make_document()
    last_seen_started = threading.Event()
    last_seen_done = threading.Event()
    last_seen_thread = threading.Thread(
        target=lambda: (
            last_seen_started.set(),
            last_seen_updater.update(make_context(), [id_of(document)]),
            last_seen_done.set(),
        ),
        daemon=True,
    )
    observed_blocked: list[bool] = []

    def start_last_seen_during_the_registration() -> None:
        last_seen_thread.start()
        assert last_seen_started.wait(JOIN_TIMEOUT_SECONDS)
        observed_blocked.append(not last_seen_done.wait(BLOCKED_PROBE_SECONDS))

    search_index.behavior.before(ops.CREATE, start_last_seen_during_the_registration)

    registrar.register(make_context(), [document])

    assert observed_blocked == [True]
    assert last_seen_done.wait(JOIN_TIMEOUT_SECONDS)
    last_seen_thread.join(JOIN_TIMEOUT_SECONDS)
    # 登録のあとに `last-seen` が実行され、作成済みの文書の `last_seen_at` を読む(noop)。
    assert search_index.behavior.calls_of(ops.RAISE_LAST_SEEN_AT)


@pytest.mark.usefixtures("running_crawl")
def test_start_notification_is_not_blocked_by_a_registration_of_the_same_source(
    registrar: DocumentRegistrar,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    clock: FixedClock,
) -> None:
    """開始・終了通知のロックは、登録・`last-seen` のロックとは別のインスタンス(案 19)。"""
    crawl_runs = CrawlRuns(
        config=LifecycleConfig(
            skip_oversize_id_limit=5, write_conflict_max_rereads=3, deletion_retention_count=3
        ),
        deletions_store=deletions_store,
        clock=clock,
        wake=lambda: None,
    )
    start_finished = threading.Event()
    observed: list[bool] = []

    def start_during_the_registration() -> None:
        notifier = threading.Thread(
            target=lambda: (
                crawl_runs.start_crawl(make_start(crawl_id="job-next")),
                start_finished.set(),
            ),
            daemon=True,
        )
        notifier.start()
        # 同じソースの登録の処理中(PUT の直前)でも、開始通知は待たされずに終わる。
        observed.append(start_finished.wait(JOIN_TIMEOUT_SECONDS))
        notifier.join(JOIN_TIMEOUT_SECONDS)

    search_index.behavior.before(ops.CREATE, start_during_the_registration)

    registrar.register(make_context(), [make_document()])

    assert observed == [True]
