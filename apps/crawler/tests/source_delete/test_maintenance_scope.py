"""メンテナンスフラグの範囲(architecture 8.1・7.9。module 4.6)を、途中で立つ場合も含めて固定する。

フラグを確認するのは、順 1・2・4 の Indexer への要請の前だけ(各 1 回)。順 3(Crawler 自身の記録の
削除)と順 5(設定の削除)の前には確認しない。したがって:
- 順 2 の最中にフラグが立っても、順 3 は実行され、順 4 の前で `failed(maintenance)` で止まる。
  フラグを下ろして再実行すれば、順 1〜5 が冪等に完了する(止めても安全性は増えない)。
- 順 4 の最中に立っても、順 5 は実行される(順 5 は順 4 の成功後にだけ到達する)。
"""

from loreley_crawler.jobs import Accepted
from loreley_crawler.jobs.records import MAINTENANCE_RECORD_ID
from tests.fakes import in_memory_repository as ops
from tests.fakes.fake_indexer_client import (
    DELETE_DELETION_RECORDS,
    DELETE_DOCUMENTS,
    DISCARD_DELETIONS,
)
from tests.jobs.support import ADMITTED_JOB_ID, LOCK_ID, SOURCE_ID
from tests.source_delete.support import (
    INDEXER_STEPS,
    SKIP_ID,
    TimelineIndexerClient,
    make_admission,
    make_runner,
    new_timeline_env,
)


def seed_skip_record(jobs) -> None:
    jobs.jobs_repository.seed(
        SKIP_ID,
        {
            "record_type": "skip",
            "source_id": SOURCE_ID,
            "document_id": "aaa",
            "external_id": "a.txt",
        },
    )


def flag_reads(jobs) -> int:
    return len(
        [
            call
            for call in jobs.jobs_repository.behavior.calls
            if call.operation == ops.FETCH and call.key == MAINTENANCE_RECORD_ID
        ]
    )


def test_the_flag_is_read_only_before_the_three_indexer_steps() -> None:
    events: list[str] = []
    jobs = new_timeline_env(events)
    jobs.seed_source()
    seed_skip_record(jobs)
    indexer = TimelineIndexerClient(events)
    assert isinstance(make_admission(jobs).accept_source_delete(SOURCE_ID), Accepted)
    reads_at_admission = flag_reads(jobs)
    reads_before_each_step: list[int] = []
    for step in INDEXER_STEPS:
        indexer.behavior.before(step, lambda: reads_before_each_step.append(flag_reads(jobs)))

    make_runner(jobs, indexer).run_next()

    assert jobs.job_body(ADMITTED_JOB_ID)["status"] == "succeeded"
    # 順 1・2・4 の各要請の前に 1 回ずつ。順 3・5 の前には読まない(合計 3 回)。
    assert [reads - reads_at_admission for reads in reads_before_each_step] == [1, 2, 3]
    assert flag_reads(jobs) - reads_at_admission == 3
    assert jobs.sources_repository.body_of(SOURCE_ID) is None


def test_a_flag_raised_during_step_2_still_runs_step_3_and_stops_before_step_4() -> None:
    events: list[str] = []
    jobs = new_timeline_env(events)
    jobs.seed_source()
    seed_skip_record(jobs)
    indexer = TimelineIndexerClient(events)
    indexer.behavior.before(DELETE_DOCUMENTS, lambda: jobs.seed_maintenance(True))
    assert isinstance(make_admission(jobs).accept_source_delete(SOURCE_ID), Accepted)
    runner = make_runner(jobs, indexer)

    runner.run_next()

    body = jobs.job_body(ADMITTED_JOB_ID)
    assert (body["status"], body["failure_reason"]) == ("failed", "maintenance")
    assert indexer.operations() == [DISCARD_DELETIONS, DELETE_DOCUMENTS]  # 順 4 は呼ばない
    assert jobs.jobs_repository.body_of(SKIP_ID) is None  # 順 3 は実行された
    source = jobs.sources_repository.body_of(SOURCE_ID)
    assert source is not None and source["status"] == "deleting"  # 順 5 は行わない
    assert jobs.lock_body() is None  # 最終状態を記録でき、所有も失っていない

    # フラグを下ろして再実行すると、冪等に完了する。
    jobs.seed_maintenance(False)
    jobs.clock.advance(seconds=1)
    second = make_admission(jobs).accept_source_delete(SOURCE_ID)
    assert isinstance(second, Accepted)
    runner.run_next()

    assert jobs.job_body(second.job.job_id)["status"] == "succeeded"
    assert jobs.sources_repository.body_of(SOURCE_ID) is None
    assert jobs.jobs_repository.body_of(LOCK_ID) is None
    assert indexer.operations()[-3:] == INDEXER_STEPS


def test_a_flag_raised_during_step_4_does_not_stop_step_5() -> None:
    events: list[str] = []
    jobs = new_timeline_env(events)
    jobs.seed_source()
    indexer = TimelineIndexerClient(events)
    indexer.behavior.before(DELETE_DELETION_RECORDS, lambda: jobs.seed_maintenance(True))
    assert isinstance(make_admission(jobs).accept_source_delete(SOURCE_ID), Accepted)
    reads_at_admission = flag_reads(jobs)

    make_runner(jobs, indexer).run_next()

    # 順 5 は、順 4 が成功した後にだけ到達する。その前にはフラグを読み直さない。
    assert jobs.job_body(ADMITTED_JOB_ID)["status"] == "succeeded"
    assert jobs.sources_repository.body_of(SOURCE_ID) is None
    assert jobs.lock_body() is None
    assert flag_reads(jobs) - reads_at_admission == 3


def test_a_flag_raised_during_step_1_stops_before_step_2_and_nothing_is_deleted() -> None:
    events: list[str] = []
    jobs = new_timeline_env(events)
    jobs.seed_source()
    seed_skip_record(jobs)
    indexer = TimelineIndexerClient(events)
    indexer.behavior.before(DISCARD_DELETIONS, lambda: jobs.seed_maintenance(True))
    assert isinstance(make_admission(jobs).accept_source_delete(SOURCE_ID), Accepted)

    make_runner(jobs, indexer).run_next()

    body = jobs.job_body(ADMITTED_JOB_ID)
    assert (body["status"], body["failure_reason"]) == ("failed", "maintenance")
    assert indexer.operations() == [DISCARD_DELETIONS]
    assert jobs.jobs_repository.body_of(SKIP_ID) is not None  # 順 3 に進んでいない
