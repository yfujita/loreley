"""受付 → Job Runner → `SourceDeleteExecutor` の結合(#16)。

本物の受付・Job Runner・ハートビート・ロックで、ロックが最後まで残ること、途中停止後の再実行で
完了すること、`deleting` のソースにクロールを起動できないことを確かめる。
"""

from loreley_crawler.infrastructure.indexer_client import IndexerRejected, IndexerUnavailable
from loreley_crawler.jobs import (
    Accepted,
    LockAlreadyHeld,
    MaintenanceEnabled,
    SourceConfigNotFound,
    SourceDeleting,
)
from loreley_crawler.jobs.locks import Heartbeat
from tests.fakes.fake_indexer_client import DELETE_DOCUMENTS, DISCARD_DELETIONS
from tests.jobs.support import ADMITTED_JOB_ID, LOCK_ID, SOURCE_ID
from tests.source_delete.support import (
    INDEXER_STEPS,
    TimelineIndexerClient,
    make_admission,
    make_runner,
    new_timeline_env,
)


def test_the_lock_is_held_to_the_end_and_deleted_last_by_the_runner() -> None:
    events: list[str] = []
    jobs = new_timeline_env(events)
    jobs.seed_source()
    indexer = TimelineIndexerClient(events)
    heartbeats: list[Heartbeat] = []
    held_at_each_step: list[bool] = []

    def lock_is_held() -> None:
        lock = jobs.lock_body()
        held_at_each_step.append(lock is not None and lock["job_id"] == ADMITTED_JOB_ID)

    for step in INDEXER_STEPS:
        indexer.behavior.before(step, lock_is_held)
    result = make_admission(jobs).accept_source_delete(SOURCE_ID)
    assert isinstance(result, Accepted)
    events.clear()

    assert make_runner(jobs, indexer, heartbeats).run_next() is True

    body = jobs.job_body(ADMITTED_JOB_ID)
    assert body["status"] == "succeeded"
    assert held_at_each_step == [True, True, True]
    assert jobs.lock_body() is None
    assert jobs.sources_repository.body_of(SOURCE_ID) is None
    # ロック文書の削除は、設定の削除と最終状態の記録の後(最後)。
    last_lock_delete = len(events) - 1 - events[::-1].index(f"jobs:delete:{LOCK_ID}")
    assert events.index("sources:delete:docs") < last_lock_delete
    assert events.index(f"jobs:replace:{ADMITTED_JOB_ID}") < last_lock_delete
    assert events[-1] == f"jobs:delete:{LOCK_ID}"
    # ハートビートは最後まで動き、Job Runner が止めた(喪失の記録なし)。
    assert len(heartbeats) == 1 and heartbeats[0].lost_reason is None


def test_a_stopped_job_is_completed_by_running_the_delete_again() -> None:
    events: list[str] = []
    jobs = new_timeline_env(events)
    jobs.seed_source()
    indexer = TimelineIndexerClient(events)
    indexer.behavior.inject(DELETE_DOCUMENTS, IndexerUnavailable("http_503"), times=3)
    admission = make_admission(jobs)
    runner = make_runner(jobs, indexer)

    assert isinstance(admission.accept_source_delete(SOURCE_ID), Accepted)
    runner.run_next()

    first = jobs.job_body(ADMITTED_JOB_ID)
    assert (first["status"], first["failure_reason"]) == ("failed", "indexer_unavailable")
    # 最終状態を記録でき、所有も失っていないので、Job Runner はロックを解放する。
    assert jobs.lock_body() is None
    source = jobs.sources_repository.body_of(SOURCE_ID)
    assert source is not None and source["status"] == "deleting"

    # `deleting` のソースにも、ソース削除は受け付けられる(再実行)。
    jobs.clock.advance(seconds=1)
    second_result = admission.accept_source_delete(SOURCE_ID)
    assert isinstance(second_result, Accepted)
    runner.run_next()

    assert jobs.job_body(second_result.job.job_id)["status"] == "succeeded"
    assert jobs.sources_repository.body_of(SOURCE_ID) is None
    assert jobs.lock_body() is None
    # 2 回目は、順 1 から全部をやり直す(順 1・2・4 は冪等)。
    assert indexer.operations()[-3:] == INDEXER_STEPS


def test_a_deleting_source_cannot_start_a_crawl_even_after_the_delete_failed() -> None:
    events: list[str] = []
    jobs = new_timeline_env(events)
    jobs.seed_source()
    indexer = TimelineIndexerClient(events)
    indexer.behavior.inject(DISCARD_DELETIONS, IndexerRejected(400, "invalid_request"))
    admission = make_admission(jobs)
    crawl_attempts: list[object] = []

    def try_to_start_a_crawl() -> None:
        crawl_attempts.append(admission.accept_manual_crawl(SOURCE_ID))
        crawl_attempts.append(admission.accept_scheduled_crawl(SOURCE_ID))

    indexer.behavior.before(DISCARD_DELETIONS, try_to_start_a_crawl)
    assert isinstance(admission.accept_source_delete(SOURCE_ID), Accepted)

    make_runner(jobs, indexer).run_next()

    # 実行中: `deleting` が先に判定される(ロックより前)。
    assert [type(r) for r in crawl_attempts] == [SourceDeleting, SourceDeleting]
    # 失敗した後(ロックは解放済み)も、`deleting` が残るので起動できない。
    assert jobs.job_body(ADMITTED_JOB_ID)["status"] == "failed"
    assert jobs.lock_body() is None
    assert isinstance(admission.accept_manual_crawl(SOURCE_ID), SourceDeleting)
    assert isinstance(admission.accept_scheduled_crawl(SOURCE_ID), SourceDeleting)


def test_a_lost_lock_is_kept_by_the_runner_and_blocks_a_new_delete_until_released() -> None:
    events: list[str] = []
    jobs = new_timeline_env(events)
    jobs.seed_source()
    indexer = TimelineIndexerClient(events)
    indexer.behavior.inject(DELETE_DOCUMENTS, IndexerRejected(409, "lock_not_owned"))
    admission = make_admission(jobs)
    assert isinstance(admission.accept_source_delete(SOURCE_ID), Accepted)

    make_runner(jobs, indexer).run_next()

    body = jobs.job_body(ADMITTED_JOB_ID)
    assert (body["status"], body["failure_reason"]) == ("failed", "lock_lost")
    lock = jobs.lock_body()
    assert lock is not None and lock["job_id"] == ADMITTED_JOB_ID  # 喪失時は削除しない
    # 別のジョブ ID(別の乱数)の受付は、保持中のロックで拒否される。
    another = make_admission(jobs, random_token=lambda: "1111abcd")
    assert isinstance(another.accept_source_delete(SOURCE_ID), LockAlreadyHeld)
    assert indexer.operations() == [DISCARD_DELETIONS, DELETE_DOCUMENTS]


def test_a_flag_raised_before_the_run_fails_the_job_with_maintenance_and_the_lock_is_released() -> (
    None
):
    events: list[str] = []
    jobs = new_timeline_env(events)
    jobs.seed_source()
    indexer = TimelineIndexerClient(events)
    admission = make_admission(jobs)
    assert isinstance(admission.accept_source_delete(SOURCE_ID), Accepted)
    jobs.seed_maintenance(True)

    make_runner(jobs, indexer).run_next()

    body = jobs.job_body(ADMITTED_JOB_ID)
    assert (body["status"], body["failure_reason"]) == ("failed", "maintenance")
    assert indexer.operations() == []
    assert jobs.lock_body() is None  # 最終状態を記録でき、所有も失っていない
    assert isinstance(admission.accept_source_delete(SOURCE_ID), MaintenanceEnabled)


def test_a_delete_of_a_missing_config_is_not_accepted() -> None:
    jobs = new_timeline_env([])

    assert isinstance(make_admission(jobs).accept_source_delete(SOURCE_ID), SourceConfigNotFound)
