"""起動時の回復(architecture 5.8。module 5.7。テスト観点 #15・#27)。

対象は `owner` が自分のロックとジョブだけ。`running` は `failed`(`crawler_restart`)、孤児ロックと
終端のジョブのロックは削除、`queued` のジョブはロックごとそのまま残す。
"""

import logging

import pytest

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.infrastructure.opensearch import StoredRecord
from loreley_crawler.jobs import JobStatus, JobType, RecoveryReport, StartupRecovery
from tests.fakes import in_memory_repository as ops
from tests.jobs.support import (
    JOB_ID,
    NO_WAIT_RETRIER,
    OTHER_JOB_ID,
    OTHER_OWNER,
    OWNER,
    SOURCE_ID,
    JobsEnv,
    make_env,
)

LEASE = "2026-11-13T00:05:00.000Z"
SECOND_SOURCE = "wiki"


def make_recovery(env: JobsEnv) -> StartupRecovery:
    return StartupRecovery(
        settings=env.settings,
        job_store=env.job_store,
        lock_store=env.lock_store,
        clock=env.clock,
        retrier=NO_WAIT_RETRIER,
    )


# --- 手順 1: running のジョブ ---


def test_a_running_job_becomes_failed_with_crawler_restart_and_its_lock_is_deleted() -> None:
    env = make_env()
    env.seed_job(
        JOB_ID,
        status=JobStatus.RUNNING,
        started_at="2026-11-12T23:00:00.000Z",
        registration={"partial": True, "enumerated_count": 5},
    )
    env.seed_lock(JOB_ID, lease_expires_at=LEASE)

    report = make_recovery(env).run()

    assert report == RecoveryReport((JOB_ID,), (SOURCE_ID,), ())
    body = env.job_body(JOB_ID)
    assert body["status"] == "failed"
    assert body["failure_reason"] == "crawler_restart"
    assert body["finished_at"] == "2026-11-13T00:00:00.000Z"
    assert env.lock_body() is None


def test_the_registration_result_and_other_fields_are_left_as_they_were() -> None:
    env = make_env()
    registration = {"partial": False, "enumerated_count": 7}
    env.seed_job(
        JOB_ID,
        status=JobStatus.RUNNING,
        registration=registration,
        finish_notice={"send_started_at": "2026-11-12T23:30:00.000Z"},
    )

    make_recovery(env).run()

    body = env.job_body(JOB_ID)
    assert body["registration"] == registration
    assert body["finish_notice"] == {"send_started_at": "2026-11-12T23:30:00.000Z"}
    assert "confirmation" not in body  # ポーリング中だったジョブにも、確認結果の区分は書かない


def test_a_running_job_without_a_lock_is_failed_too() -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING)

    report = make_recovery(env).run()

    assert report.failed_job_ids == (JOB_ID,)
    assert env.job_body(JOB_ID)["failure_reason"] == "crawler_restart"


def test_a_running_source_delete_is_failed_too() -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING, job_type=JobType.SOURCE_DELETE)
    env.seed_lock(JOB_ID)

    make_recovery(env).run()

    assert env.job_body(JOB_ID)["failure_reason"] == "crawler_restart"
    assert env.lock_body() is None


def test_the_cancel_request_does_not_survive_a_restart_and_the_job_fails() -> None:  # 観点 #27
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    env.cancel_requests.request(JOB_ID)

    restarted = make_env(env.jobs_repository)  # 再起動: 新しいレジストリ
    make_recovery(restarted).run()

    assert not restarted.cancel_requests.is_requested(JOB_ID)
    assert env.job_body(JOB_ID)["status"] == "failed"  # `cancelled` ではなく `failed`
    assert env.job_body(JOB_ID)["failure_reason"] == "crawler_restart"


# --- 手順 2: 削除するロック ---


def test_an_orphan_lock_without_a_job_record_is_deleted() -> None:
    env = make_env()
    env.seed_lock(JOB_ID)

    report = make_recovery(env).run()

    assert report == RecoveryReport((), (SOURCE_ID,), ())
    assert env.lock_body() is None


@pytest.mark.parametrize("job_id", [None, 5, ""])
def test_a_lock_without_a_readable_job_id_is_an_orphan_and_is_deleted(job_id: object) -> None:
    """運用者の手編集などで `job_id` が欠けたロックでも、回復が落ちずに孤児ロックとして消す。"""
    env = make_env()
    env.seed_lock(JOB_ID)
    env.jobs_repository.seed(f"lock-{SOURCE_ID}", {**(env.lock_body() or {}), "job_id": job_id})

    report = make_recovery(env).run()

    assert report == RecoveryReport((), (SOURCE_ID,), ())
    assert env.lock_body() is None


@pytest.mark.parametrize(
    "status",
    [JobStatus.SUCCEEDED, JobStatus.PARTIALLY_SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED],
)
def test_the_lock_of_a_terminal_job_is_deleted_and_the_job_is_unchanged(
    status: JobStatus,
) -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=status)
    env.seed_lock(JOB_ID)
    before = env.job_body(JOB_ID)

    report = make_recovery(env).run()

    assert report.deleted_lock_source_ids == (SOURCE_ID,)
    assert env.lock_body() is None
    assert env.job_body(JOB_ID) == before


def test_a_lock_whose_version_moved_is_reread_and_deleted() -> None:
    env = make_env()
    env.seed_lock(JOB_ID)
    env.jobs_repository.behavior.before(
        ops.DELETE,
        lambda: env.jobs_repository.seed(f"lock-{SOURCE_ID}", env.lock_body() or {}),
        key=f"lock-{SOURCE_ID}",
    )

    make_recovery(env).run()

    assert env.lock_body() is None


# --- 手順 3: queued のジョブ ---


@pytest.mark.parametrize("lease", [None, LEASE])
def test_a_queued_job_and_its_lock_are_left_as_they_were(lease: str | None) -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.QUEUED)
    env.seed_lock(JOB_ID, lease_expires_at=lease)
    job_before = env.job_body(JOB_ID)
    lock_before = env.lock_body()

    report = make_recovery(env).run()

    assert report == RecoveryReport((), (), (SOURCE_ID,))
    assert env.job_body(JOB_ID) == job_before
    assert env.lock_body() == lock_before
    assert env.jobs_repository.write_calls() == []


# --- 手順 4: owner が自分以外 ---


def test_a_lock_of_another_owner_is_not_touched_and_is_warned(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.FAILED, owner=OTHER_OWNER)
    env.seed_lock(JOB_ID, owner=OTHER_OWNER)

    with caplog.at_level(logging.WARNING):
        report = make_recovery(env).run()

    assert report == RecoveryReport((), (), (SOURCE_ID,))
    assert env.lock_body() is not None
    assert "another crawler" in caplog.text
    assert env.jobs_repository.write_calls() == []


def test_a_running_job_of_another_owner_is_not_failed() -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING, owner=OTHER_OWNER)
    env.seed_lock(JOB_ID, owner=OTHER_OWNER)

    report = make_recovery(env).run()

    assert report == RecoveryReport((), (), (SOURCE_ID,))
    assert env.job_body(JOB_ID)["status"] == "running"


def test_a_lock_of_ours_that_points_to_a_running_job_of_another_owner_is_kept(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING, owner=OTHER_OWNER)
    env.seed_lock(JOB_ID, owner=OWNER)

    with caplog.at_level(logging.WARNING):
        report = make_recovery(env).run()

    assert report.deleted_lock_source_ids == ()
    assert env.lock_body() is not None
    assert "not ours" in caplog.text


# --- まとめて・異常系 ---


def test_a_mixed_state_is_recovered_source_by_source() -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    env.seed_lock(JOB_ID)
    env.seed_job(OTHER_JOB_ID, status=JobStatus.QUEUED, source_id=SECOND_SOURCE)
    env.seed_lock(OTHER_JOB_ID, source_id=SECOND_SOURCE)
    env.seed_lock("job-20261113T000000Z-0000beef", source_id="orphan-source")

    report = make_recovery(env).run()

    assert report.failed_job_ids == (JOB_ID,)
    assert sorted(report.deleted_lock_source_ids) == ["docs", "orphan-source"]
    assert report.kept_lock_source_ids == (SECOND_SOURCE,)
    assert env.job_body(OTHER_JOB_ID)["status"] == "queued"
    assert env.lock_body(SECOND_SOURCE) is not None


@pytest.mark.parametrize("broken", ["9999-12-31T23:59:59-05:00", "0001-01-01T00:00:00+09:00"])
@pytest.mark.parametrize("field", ["lease_expires_at", "acquired_at"])
def test_one_lock_with_an_out_of_range_date_does_not_fail_the_whole_recovery(
    field: str, broken: str
) -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    env.seed_lock(JOB_ID)
    env.jobs_repository.seed(f"lock-{SOURCE_ID}", {**(env.lock_body() or {}), field: broken})
    env.seed_job(OTHER_JOB_ID, status=JobStatus.QUEUED, source_id=SECOND_SOURCE)
    env.seed_lock(OTHER_JOB_ID, source_id=SECOND_SOURCE)

    report = make_recovery(env).run()

    assert report == RecoveryReport((JOB_ID,), (SOURCE_ID,), (SECOND_SOURCE,))
    assert env.lock_body() is None


@pytest.mark.parametrize("status", ["garbage", None, 5])
def test_a_lock_of_a_job_with_an_unreadable_status_is_left_alone_and_recovery_goes_on(
    status: object, caplog: pytest.LogCaptureFixture
) -> None:
    """状態が読めないジョブのロックは、判断できないので触らない。回復全体は止めない。"""
    env = make_env()
    env.seed_job(JOB_ID)
    env.jobs_repository.seed(JOB_ID, {**env.job_body(JOB_ID), "status": status})
    env.seed_lock(JOB_ID)
    broken_job_before = env.job_body(JOB_ID)
    broken_lock_before = env.lock_body()
    # 他のソースの回復は進む(`running` の失敗・孤児ロックの削除・`queued` の保持)。
    env.seed_job(OTHER_JOB_ID, status=JobStatus.RUNNING, source_id="wiki")
    env.seed_lock(OTHER_JOB_ID, source_id="wiki")
    env.seed_lock("job-20261113T000000Z-0000beef", source_id="orphan-source")
    env.seed_job("job-q", status=JobStatus.QUEUED, source_id="queued-source")
    env.seed_lock("job-q", source_id="queued-source")

    with caplog.at_level(logging.WARNING):
        report = make_recovery(env).run()

    assert report.failed_job_ids == (OTHER_JOB_ID,)
    assert sorted(report.deleted_lock_source_ids) == ["orphan-source", "wiki"]
    assert sorted(report.kept_lock_source_ids) == ["docs", "queued-source"]
    assert env.job_body(JOB_ID) == broken_job_before
    assert env.lock_body() == broken_lock_before
    assert f"job_id={JOB_ID}" in caplog.text
    assert "unreadable status" in caplog.text
    assert "garbage" not in caplog.text


def test_a_job_with_other_malformed_fields_does_not_stop_the_recovery_of_a_running_job() -> None:
    """`running` の失敗は `status` だけを使う。`job_type`・`source_id` が壊れていても落ちない。"""
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    env.jobs_repository.seed(
        JOB_ID, {**env.job_body(JOB_ID), "job_type": "garbage", "source_id": 5}
    )
    env.seed_lock(JOB_ID)

    report = make_recovery(env).run()

    assert report.failed_job_ids == (JOB_ID,)
    assert env.job_body(JOB_ID)["failure_reason"] == "crawler_restart"
    assert env.lock_body() is None


def test_an_unexpected_store_response_while_reading_the_job_is_not_swallowed() -> None:
    env = make_env()
    env.seed_lock(JOB_ID)
    env.jobs_repository.behavior.inject(
        ops.FETCH, StoreUnexpectedResponseError("non_unique_sort"), key=JOB_ID
    )

    with pytest.raises(StoreUnexpectedResponseError) as raised:
        make_recovery(env).run()

    assert raised.value.error_type == "non_unique_sort"


@pytest.mark.parametrize("owner", [None, 5, ""])
def test_a_lock_with_a_broken_owner_is_not_touched_by_the_recovery(
    owner: object, caplog: pytest.LogCaptureFixture
) -> None:
    """壊れた `owner` は、他の Crawler のロックとして触らない(管理者のロック解放で消す)。"""
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.FAILED)
    env.seed_lock(JOB_ID)
    env.jobs_repository.seed(f"lock-{SOURCE_ID}", {**(env.lock_body() or {}), "owner": owner})
    before = env.lock_body()

    with caplog.at_level(logging.WARNING):
        report = make_recovery(env).run()

    assert report == RecoveryReport((), (), (SOURCE_ID,))
    assert env.lock_body() == before
    assert "another crawler" in caplog.text


def test_a_recovery_of_nothing_is_a_no_op() -> None:
    env = make_env()

    assert make_recovery(env).run() == RecoveryReport((), (), ())
    assert env.jobs_repository.write_calls() == []


def test_a_transient_store_error_is_retried_and_a_persistent_one_is_raised() -> None:
    env = make_env()
    env.seed_lock(JOB_ID)
    env.jobs_repository.behavior.inject(ops.LIST, StoreUnavailableError("timeout"), times=2)

    assert make_recovery(env).run().deleted_lock_source_ids == (SOURCE_ID,)

    env.seed_lock(JOB_ID)
    env.jobs_repository.behavior.inject(ops.LIST, StoreUnavailableError("timeout"), times=None)
    with pytest.raises(StoreUnavailableError):
        make_recovery(env).run()


def test_a_transient_error_listing_the_locks_is_retried() -> None:
    env = make_env()
    env.seed_lock(JOB_ID)
    behavior = env.jobs_repository.behavior
    behavior.before(ops.LIST, lambda: None)  # 1 回目の一覧(実行中のジョブ)は通す
    behavior.before(
        ops.LIST,
        lambda: behavior.inject(ops.LIST, StoreUnavailableError("timeout"), times=2),
    )

    report = make_recovery(env).run()

    assert report.deleted_lock_source_ids == (SOURCE_ID,)


def test_a_truncated_lock_list_is_not_treated_as_complete() -> None:
    env = make_env()
    full_page = [
        StoredRecord(f"lock-s{i}", {"record_type": "lock", "owner": OWNER}, i, 1)
        for i in range(10_000)
    ]
    env.jobs_repository.behavior.inject(ops.LIST, [], times=1)  # 1 回目: 実行中のジョブの一覧
    env.jobs_repository.behavior.inject(ops.LIST, full_page, times=1)

    with pytest.raises(StoreUnexpectedResponseError) as raised:
        make_recovery(env).run()

    assert raised.value.error_type == "lock_list_truncated"
