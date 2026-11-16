"""ロック解放(管理者)(architecture 5.4。crawler-api 4.3。テスト観点 #28・#29)。

解放するもの・しないものを、ロック文書とジョブの状態の組ごとに確かめる。解放と Job Runner の更新の
競合は、fake の割り込みフックで両方の先後を再現する(ロックの削除が先、ジョブの `failed` が後)。
"""

import logging
from datetime import timedelta

import pytest

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.jobs import (
    ExistingJob,
    JobStatus,
    JobTrigger,
    JobType,
    LockInUse,
    LockRelease,
    LockReleased,
    NoLockToRelease,
)
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW
from tests.fakes.lost_response_repository import LostResponseRepository
from tests.jobs.support import (
    JOB_ID,
    LOCK_ID,
    NO_WAIT_RETRIER,
    SOURCE_ID,
    JobsEnv,
    make_env,
)

EXPIRED_LEASE = "2026-11-12T23:59:59.999Z"
ACTIVE_LEASE = "2026-11-13T00:05:00.000Z"
LONG_AGO = DEFAULT_NOW - timedelta(hours=1)


def make_release(env: JobsEnv) -> LockRelease:
    return LockRelease(
        settings=env.settings,
        job_store=env.job_store,
        lock_store=env.lock_store,
        clock=env.clock,
        retrier=NO_WAIT_RETRIER,
    )


# --- ロック文書がない ---


def test_no_lock_means_nothing_to_release() -> None:
    env = make_env()

    assert make_release(env).release(SOURCE_ID) == NoLockToRelease()
    assert env.jobs_repository.write_calls() == []


def test_releasing_twice_is_idempotent() -> None:
    env = make_env()
    env.seed_lock(JOB_ID, acquired_at=LONG_AGO)
    release = make_release(env)

    assert release.release(SOURCE_ID) == LockReleased(None)
    assert release.release(SOURCE_ID) == NoLockToRelease()


def test_the_source_config_does_not_have_to_exist() -> None:
    """ソース削除の完了後に、ロック文書だけが残った場合も解放できる(architecture 8.3)。"""
    env = make_env()
    env.seed_lock(JOB_ID, acquired_at=LONG_AGO)

    assert make_release(env).release(SOURCE_ID) == LockReleased(None)
    assert env.sources_repository.record_ids() == []


# --- ジョブ記録がない(孤児ロック・受付の途中) ---


def test_an_orphan_lock_that_is_not_recent_is_released() -> None:
    env = make_env()
    env.seed_lock(JOB_ID, acquired_at=LONG_AGO)

    assert make_release(env).release(SOURCE_ID) == LockReleased(None)
    assert env.lock_body() is None


def test_a_lock_without_a_job_that_was_just_acquired_is_not_released() -> None:  # テスト観点 #29
    env = make_env()
    env.seed_lock(JOB_ID, acquired_at=DEFAULT_NOW - timedelta(seconds=59.999))

    result = make_release(env).release(SOURCE_ID)

    assert result == LockInUse(ExistingJob(JOB_ID, None, None, None, None))
    assert env.lock_body() is not None
    assert env.jobs_repository.write_calls() == []


def test_the_recent_boundary_is_the_admitting_grace_seconds() -> None:
    env = make_env()
    env.seed_lock(JOB_ID, acquired_at=DEFAULT_NOW - timedelta(seconds=60))

    assert make_release(env).release(SOURCE_ID) == LockReleased(None)  # ちょうど 60 秒は直近でない


@pytest.mark.parametrize("acquired_at", [None, "not-a-date", 123, "2026-11-12T00:00:00"])
def test_a_missing_or_malformed_acquired_at_is_treated_as_old(acquired_at: object) -> None:
    env = make_env()
    env.seed_lock(JOB_ID, acquired_at=DEFAULT_NOW)
    env.jobs_repository.seed(LOCK_ID, {**(env.lock_body() or {}), "acquired_at": acquired_at})

    assert make_release(env).release(SOURCE_ID) == LockReleased(None)


# --- ジョブが終端・queued・running ---


@pytest.mark.parametrize(
    "status",
    [JobStatus.SUCCEEDED, JobStatus.PARTIALLY_SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED],
)
def test_the_lock_of_a_terminal_job_is_released_without_touching_the_job(
    status: JobStatus,
) -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=status)
    env.seed_lock(JOB_ID, acquired_at=DEFAULT_NOW)
    before = env.job_body(JOB_ID)

    assert make_release(env).release(SOURCE_ID) == LockReleased(None)

    assert env.lock_body() is None
    assert env.job_body(JOB_ID) == before


@pytest.mark.parametrize("lease", [None, EXPIRED_LEASE, ACTIVE_LEASE])
def test_the_lock_of_a_queued_job_is_never_released(lease: str | None) -> None:  # テスト観点 #29
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.QUEUED)
    env.seed_lock(JOB_ID, acquired_at=LONG_AGO, lease_expires_at=lease)

    result = make_release(env).release(SOURCE_ID)

    assert isinstance(result, LockInUse)
    assert result.existing_job.status is JobStatus.QUEUED
    assert env.lock_body() is not None
    assert env.job_body(JOB_ID)["status"] == "queued"


def test_a_running_job_within_its_lease_is_in_use() -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    lock = env.seed_lock(JOB_ID, acquired_at=LONG_AGO, lease_expires_at=ACTIVE_LEASE)

    result = make_release(env).release(SOURCE_ID)

    assert result == LockInUse(
        ExistingJob(
            JOB_ID, JobType.CRAWL, JobStatus.RUNNING, JobTrigger.MANUAL, lock.lease_expires_at
        )
    )
    assert env.lock_body() is not None
    assert env.job_body(JOB_ID)["status"] == "running"


def test_the_lease_boundary_is_the_expiry_instant() -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    env.seed_lock(JOB_ID, acquired_at=LONG_AGO, lease_expires_at="2026-11-13T00:00:00.001Z")
    release = make_release(env)

    assert isinstance(release.release(SOURCE_ID), LockInUse)

    env.clock.advance(seconds=0.001)  # 期限ちょうど(Indexer は期限以降を「所有していない」とする)
    assert release.release(SOURCE_ID) == LockReleased(JOB_ID)


@pytest.mark.parametrize("lease", [EXPIRED_LEASE, None, "garbage", 5])
def test_an_expired_missing_or_malformed_lease_releases_and_fails_the_running_job(
    lease: object,
) -> None:
    env = make_env()
    env.seed_job(
        JOB_ID,
        status=JobStatus.RUNNING,
        started_at="2026-11-12T00:00:00.000Z",
        registration={"partial": True},
    )
    env.seed_lock(JOB_ID, acquired_at=LONG_AGO, lease_expires_at=lease)

    result = make_release(env).release(SOURCE_ID)

    assert result == LockReleased(JOB_ID)
    assert env.lock_body() is None
    body = env.job_body(JOB_ID)
    assert body["status"] == "failed"
    assert body["failure_reason"] == "lock_released"
    assert body["finished_at"] == "2026-11-13T00:00:00.000Z"
    assert body["registration"] == {"partial": True}  # 他の項目は変えない
    assert body["started_at"] == "2026-11-12T00:00:00.000Z"


def test_a_source_delete_job_with_an_expired_lease_is_released_too() -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING, job_type=JobType.SOURCE_DELETE)
    env.seed_lock(JOB_ID, acquired_at=LONG_AGO, lease_expires_at=EXPIRED_LEASE)

    assert make_release(env).release(SOURCE_ID) == LockReleased(JOB_ID)
    assert env.job_body(JOB_ID)["failure_reason"] == "lock_released"


@pytest.mark.parametrize("status", ["garbage", None, 5])
def test_a_job_with_an_unreadable_status_is_not_released_but_reported_as_in_use(
    status: object,
) -> None:
    """実行中でないと判断できないので、解放しない(安全側)。500 ではなく 409 になる。"""
    env = make_env()
    env.seed_job(JOB_ID)
    env.jobs_repository.seed(JOB_ID, {**env.job_body(JOB_ID), "status": status})
    env.seed_lock(JOB_ID, acquired_at=LONG_AGO)
    before = env.job_body(JOB_ID)

    result = make_release(env).release(SOURCE_ID)

    assert result == LockInUse(ExistingJob(JOB_ID, JobType.CRAWL, None, JobTrigger.MANUAL, None))
    assert env.lock_body() is not None
    assert env.job_body(JOB_ID) == before
    assert env.jobs_repository.write_calls() == []


def test_a_lock_without_a_readable_job_id_is_released_when_it_is_old() -> None:
    """壊れたロック(`job_id` が文字列でない → 空)も、管理者が解放できる。"""
    env = make_env()
    env.seed_lock(JOB_ID, acquired_at=LONG_AGO)
    env.jobs_repository.seed(LOCK_ID, {**(env.lock_body() or {}), "job_id": None})

    assert make_release(env).release(SOURCE_ID) == LockReleased(None)
    assert env.lock_body() is None


def test_a_lock_without_a_job_id_that_was_just_acquired_is_in_use() -> None:
    env = make_env()
    env.seed_lock(JOB_ID, acquired_at=DEFAULT_NOW)
    env.jobs_repository.seed(LOCK_ID, {**(env.lock_body() or {}), "job_id": None})

    assert make_release(env).release(SOURCE_ID) == LockInUse(
        ExistingJob("", None, None, None, None)
    )
    assert env.lock_body() is not None


def test_a_failure_to_fail_the_job_after_the_delete_is_logged_with_the_job_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    seed_stalled_running_job(env)
    env.jobs_repository.behavior.inject(
        ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=None
    )

    with caplog.at_level(logging.WARNING), pytest.raises(StoreUnavailableError):
        make_release(env).release(SOURCE_ID)

    assert env.lock_body() is None  # ロックは削除済み(ロックのない `running` が残る)
    assert JOB_ID in caplog.text
    assert "could not be failed" in caplog.text


# --- ロック解放と Job Runner の競合(テスト観点 #28) ---


def seed_stalled_running_job(env: JobsEnv) -> None:
    env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    env.seed_lock(JOB_ID, acquired_at=LONG_AGO, lease_expires_at=EXPIRED_LEASE)


def test_when_the_heartbeat_resumed_before_the_delete_the_release_judges_again() -> None:
    """解放側の判定の後、ロックの削除の前に、ハートビートが再開してリースが更新された。"""
    env = make_env()
    seed_stalled_running_job(env)

    def heartbeat_resumes() -> None:
        env.seed_lock(JOB_ID, acquired_at=LONG_AGO, lease_expires_at=ACTIVE_LEASE)

    env.jobs_repository.behavior.before(ops.DELETE, heartbeat_resumes, key=LOCK_ID)

    result = make_release(env).release(SOURCE_ID)

    assert isinstance(result, LockInUse)
    assert env.lock_body() is not None
    assert env.job_body(JOB_ID)["status"] == "running"  # 生きているジョブを `failed` にしない


def test_when_the_runner_updated_the_job_first_the_release_fails_the_new_version() -> None:
    """ロックの削除の後、ジョブの更新の前に、Job Runner がジョブ記録を更新した。"""
    env = make_env()
    seed_stalled_running_job(env)

    def runner_updates_the_job() -> None:
        env.jobs_repository.seed(JOB_ID, {**env.job_body(JOB_ID), "registration": {"added": 1}})

    env.jobs_repository.behavior.before(ops.REPLACE, runner_updates_the_job, key=JOB_ID)

    result = make_release(env).release(SOURCE_ID)

    assert result == LockReleased(JOB_ID)
    body = env.job_body(JOB_ID)
    assert body["status"] == "failed"
    assert body["registration"] == {"added": 1}  # Job Runner の更新を失わない


def test_when_the_runner_already_finished_the_job_the_release_does_not_overwrite_it() -> None:
    env = make_env()
    seed_stalled_running_job(env)

    def runner_finishes_the_job() -> None:
        env.jobs_repository.seed(
            JOB_ID,
            {
                **env.job_body(JOB_ID),
                "status": "succeeded",
                "finished_at": "2026-11-13T00:00:00.000Z",
            },
        )

    env.jobs_repository.behavior.before(ops.REPLACE, runner_finishes_the_job, key=JOB_ID)

    result = make_release(env).release(SOURCE_ID)

    assert result == LockReleased(None)
    assert env.job_body(JOB_ID)["status"] == "succeeded"
    assert "failure_reason" not in env.job_body(JOB_ID)
    assert env.lock_body() is None


def test_a_lost_lock_delete_response_still_fails_the_running_job() -> None:
    repository = LostResponseRepository()
    env = make_env(repository)
    seed_stalled_running_job(env)
    repository.lose_response_of(ops.DELETE)

    result = make_release(env).release(SOURCE_ID)

    assert result == LockReleased(JOB_ID)
    assert env.lock_body() is None
    assert env.job_body(JOB_ID)["failure_reason"] == "lock_released"


def test_a_lock_replaced_by_a_new_admission_is_judged_again_not_deleted() -> None:
    env = make_env()
    env.seed_lock(JOB_ID, acquired_at=LONG_AGO)

    def new_admission_takes_the_lock() -> None:
        stored = env.jobs_repository.fetch(LOCK_ID)
        assert stored is not None
        env.jobs_repository.delete_if_unchanged(
            LOCK_ID, seq_no=stored.seq_no, primary_term=stored.primary_term
        )
        env.seed_lock("job-20261113T000000Z-0000beef", acquired_at=DEFAULT_NOW)

    env.jobs_repository.behavior.before(ops.DELETE, new_admission_takes_the_lock, key=LOCK_ID)

    result = make_release(env).release(SOURCE_ID)

    assert isinstance(result, LockInUse)  # 新しい受付の途中のロックは解放しない
    lock = env.lock_body()
    assert lock is not None
    assert lock["job_id"] == "job-20261113T000000Z-0000beef"


def test_a_contention_that_never_resolves_raises_instead_of_looping() -> None:
    env = make_env()
    env.seed_lock(JOB_ID, acquired_at=LONG_AGO)
    for _ in range(3):
        env.jobs_repository.behavior.before(
            ops.DELETE,
            lambda: env.seed_lock(JOB_ID, acquired_at=LONG_AGO),
            key=LOCK_ID,
        )

    with pytest.raises(StoreUnavailableError) as raised:
        make_release(env).release(SOURCE_ID)

    assert raised.value.reason == "lock_release_contention"


def test_a_store_failure_is_retried_then_raised() -> None:
    env = make_env()
    env.seed_lock(JOB_ID, acquired_at=LONG_AGO)
    env.jobs_repository.behavior.inject(ops.FETCH, StoreUnavailableError("timeout"), times=2)

    assert make_release(env).release(SOURCE_ID) == LockReleased(None)

    env.seed_lock(JOB_ID, acquired_at=LONG_AGO)
    env.jobs_repository.behavior.inject(ops.FETCH, StoreUnavailableError("timeout"), times=None)
    with pytest.raises(StoreUnavailableError):
        make_release(env).release(SOURCE_ID)
    assert env.lock_body() is not None
