"""`CrawlExecutor` の入口(`JobExecutor`)と、Job Runner との分担(architecture 4.8・5.5)。

最終状態は、`CrawlExecutor` が記録する。記録できたジョブは、Job Runner の最後の手段が上書きせず、
ロックを解放する。
"""

import pytest

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.infrastructure.indexer_client import FailureType
from loreley_crawler.jobs import (
    JobNotStartable,
    JobStatus,
)
from tests.crawl.support import (
    EXPECTED_LOCK,
    CrawlEnv,
    RecordingIndexerClient,
    crawl_env,
    make_runner,
)
from tests.fakes import in_memory_repository as ops
from tests.fakes.fake_indexer_client import FINISH_CRAWL, REPORT_LAST_SEEN
from tests.jobs.support import JOB_ID, SOURCE_ID, make_env


def test_the_entry_runs_a_crawl_to_its_final_state() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.executor(env.record, env.context)

        assert env.job_body()["status"] == "succeeded"
        assert env.indexer.calls_of(FINISH_CRAWL) != []
        assert env.connector.close_count == 1
        assert env.context.is_terminal


def test_a_job_that_lost_the_start_race_propagates_for_the_job_runner(env: CrawlEnv) -> None:
    env.jobs.seed_job(JOB_ID, status=JobStatus.CANCELLED)

    with pytest.raises(JobNotStartable):
        env.executor(env.record, env.context)

    assert env.indexer.calls == []


def test_the_entry_returns_after_recording_a_failure(env: CrawlEnv) -> None:
    env.jobs.sources_repository.delete_ids([SOURCE_ID])  # 設定がない

    env.executor(env.record, env.context)  # 例外なし

    assert env.job_body()["failure_reason"] == "config_invalid"


def test_the_job_runner_keeps_the_final_state_the_executor_recorded_and_releases_the_lock() -> None:
    jobs = make_env()
    jobs.seed_source()
    jobs.seed_lock(JOB_ID)
    jobs.seed_job(JOB_ID)
    indexer = RecordingIndexerClient()

    assert make_runner(jobs, indexer, {"a": b"1"}).run_next() is True

    body = jobs.job_body(JOB_ID)
    assert body["status"] == JobStatus.SUCCEEDED.value
    assert "failure_reason" not in body
    assert jobs.lock_body() is None
    # Runner が設定したロックの所有者・`job_id` を、要請に載せている(Indexer が照合する値)。
    locks = {call.arguments["lock"] for call in indexer.calls_of(REPORT_LAST_SEEN)}
    assert locks == {EXPECTED_LOCK}


def test_a_failed_crawl_is_also_released_without_being_overwritten() -> None:
    jobs = make_env()
    jobs.seed_job(JOB_ID)  # 設定がない
    jobs.seed_lock(JOB_ID)
    indexer = RecordingIndexerClient()

    assert make_runner(jobs, indexer, {}).run_next() is True

    assert jobs.job_body(JOB_ID)["failure_reason"] == "config_invalid"
    assert jobs.lock_body() is None


def test_a_lost_lock_fails_the_job_and_the_job_runner_leaves_the_lock_document() -> None:
    jobs = make_env()
    jobs.seed_source()
    jobs.seed_lock(JOB_ID)
    jobs.seed_job(JOB_ID)
    indexer = RecordingIndexerClient()
    indexer.registration_failures["a"] = FailureType.LOCK_NOT_OWNED

    assert make_runner(jobs, indexer, {"a": b"1"}).run_next() is True

    body = jobs.job_body(JOB_ID)
    assert body["failure_reason"] == "lock_lost"
    # 所有権の喪失を記録しているので、ロック文書は削除しない(回復か管理者の解放に委ねる。5.7)。
    assert jobs.lock_body() is not None
    assert [call.arguments["outcome"].value for call in indexer.calls_of(FINISH_CRAWL)] == [
        "failed"
    ]


def test_a_final_state_that_cannot_be_recorded_goes_to_the_job_runners_last_resort() -> None:
    jobs = make_env()
    jobs.seed_source()
    jobs.seed_lock(JOB_ID)
    jobs.seed_job(JOB_ID)
    indexer = RecordingIndexerClient()
    # 開始通知の後、ジョブ記録の更新がすべて失敗する(最終状態も記録できない)。
    indexer.behavior.before(
        "register_documents",
        lambda: jobs.jobs_repository.behavior.inject(
            ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=None
        ),
    )

    # Runner は、ジョブを終端にできなかったので False(走査間隔だけ待つ)を返す。
    assert make_runner(jobs, indexer, {"a": b"1"}).run_next() is False

    assert jobs.job_body(JOB_ID)["status"] == "running"
    assert (
        jobs.lock_body() is not None
    )  # 最終状態を記録できないので、ロックは解放しない(回復に委ねる)
