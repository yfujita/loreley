"""取り消し(architecture 4.7。crawler-api 4.2。テスト観点 #14・#25・#26)。

判定順(ジョブがない → `source_delete` → 終端 → 状態別)と、`queued` の取り消しと実行開始の競合
(先に条件付き更新に勝った側が有効)を確かめる。競合は fake の割り込みフックで再現する。
"""

import pytest

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.jobs import (
    Cancelled,
    CancelRequested,
    CancelRequestRegistry,
    JobAlreadyFinished,
    JobCancellation,
    JobNotCancellable,
    JobNotFound,
    JobStatus,
    JobType,
)
from loreley_crawler.jobs.records import JobSuperseded
from tests.fakes import in_memory_repository as ops
from tests.fakes.lost_response_repository import LostResponseRepository
from tests.jobs.support import (
    JOB_ID,
    LOCK_ID,
    NO_WAIT_RETRIER,
    OTHER_JOB_ID,
    OTHER_OWNER,
    SOURCE_ID,
    JobsEnv,
    make_env,
)

TERMINAL_STATUSES = [
    JobStatus.SUCCEEDED,
    JobStatus.PARTIALLY_SUCCEEDED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
]


class RecordingRegistry(CancelRequestRegistry):
    def __init__(self) -> None:
        super().__init__()
        self.requested: list[str] = []

    def request(self, job_id: str) -> None:
        self.requested.append(job_id)
        super().request(job_id)


def make_cancellation(env: JobsEnv) -> JobCancellation:
    return JobCancellation(
        job_store=env.job_store,
        lock_store=env.lock_store,
        cancel_requests=env.cancel_requests,
        clock=env.clock,
        retrier=NO_WAIT_RETRIER,
    )


# --- 判定順(crawler-api 4.2) ---


def test_an_unknown_job_is_not_found() -> None:
    assert make_cancellation(make_env()).cancel(JOB_ID) == JobNotFound()


@pytest.mark.parametrize("record_id", [LOCK_ID, "maintenance", f"skip-{SOURCE_ID}-{'a' * 64}"])
def test_a_record_that_is_not_a_job_is_not_found(record_id: str) -> None:
    env = make_env()
    env.jobs_repository.seed(record_id, {"record_type": "lock", "enabled": True})

    assert make_cancellation(env).cancel(record_id) == JobNotFound()
    assert not env.cancel_requests.is_requested(record_id)


@pytest.mark.parametrize("status", [JobStatus.QUEUED, JobStatus.RUNNING, *TERMINAL_STATUSES])
def test_a_source_delete_job_is_never_cancellable_whatever_its_status(status: JobStatus) -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=status, job_type=JobType.SOURCE_DELETE)
    env.seed_lock(JOB_ID)
    before = env.job_body(JOB_ID)

    assert make_cancellation(env).cancel(JOB_ID) == JobNotCancellable()

    assert env.job_body(JOB_ID) == before
    assert env.lock_body() is not None
    assert not env.cancel_requests.is_requested(JOB_ID)


@pytest.mark.parametrize("status", TERMINAL_STATUSES)
def test_a_finished_crawl_is_reported_with_its_status(status: JobStatus) -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=status)
    registry = RecordingRegistry()
    env.cancel_requests = registry
    before = env.job_body(JOB_ID)

    assert make_cancellation(env).cancel(JOB_ID) == JobAlreadyFinished(status)

    assert env.job_body(JOB_ID) == before
    assert env.jobs_repository.write_calls() == []
    assert registry.requested == []  # 終端のジョブには、取り消し要求を記録しない


# --- queued ---


def test_a_queued_crawl_is_cancelled_and_its_lock_is_released() -> None:  # テスト観点 #14
    env = make_env()
    env.seed_job(JOB_ID)
    env.seed_lock(JOB_ID)

    result = make_cancellation(env).cancel(JOB_ID)

    assert result == Cancelled(JOB_ID)
    body = env.job_body(JOB_ID)
    assert body["status"] == "cancelled"
    assert body["finished_at"] == "2026-11-13T00:00:00.000Z"
    assert env.lock_body() is None
    assert not env.cancel_requests.is_requested(JOB_ID)  # 取り消し要求は記録しない


def test_the_lock_with_a_lease_set_by_a_starting_runner_is_released_too() -> None:
    env = make_env()
    env.seed_job(JOB_ID)
    env.seed_lock(JOB_ID, lease_expires_at="2026-11-13T00:05:00.000Z")

    assert make_cancellation(env).cancel(JOB_ID) == Cancelled(JOB_ID)

    assert env.lock_body() is None


def test_cancelling_leaves_a_lock_that_belongs_to_another_job() -> None:
    env = make_env()
    env.seed_job(JOB_ID)
    env.seed_lock(OTHER_JOB_ID, owner=OTHER_OWNER)

    assert make_cancellation(env).cancel(JOB_ID) == Cancelled(JOB_ID)

    lock = env.lock_body()
    assert lock is not None
    assert lock["job_id"] == OTHER_JOB_ID


def test_cancelling_without_a_lock_still_cancels_the_job() -> None:
    env = make_env()
    env.seed_job(JOB_ID)

    assert make_cancellation(env).cancel(JOB_ID) == Cancelled(JOB_ID)

    assert env.job_body(JOB_ID)["status"] == "cancelled"


def test_the_lock_release_rereads_when_the_lock_version_moved() -> None:
    """ハートビートなどでロックの版が進んでも、読み直して、自分のジョブのロックなら削除する。"""
    env = make_env()
    env.seed_job(JOB_ID)
    env.seed_lock(JOB_ID)
    env.jobs_repository.behavior.before(
        ops.DELETE,
        lambda: env.jobs_repository.seed(LOCK_ID, env.lock_body() or {}),
        key=LOCK_ID,
    )

    assert make_cancellation(env).cancel(JOB_ID) == Cancelled(JOB_ID)

    assert env.lock_body() is None


def test_the_lock_release_leaves_a_lock_that_another_job_took_in_the_meantime() -> None:
    env = make_env()
    env.seed_job(JOB_ID)
    env.seed_lock(JOB_ID)

    def another_job_takes_the_lock() -> None:
        env.seed_lock(OTHER_JOB_ID, owner=OTHER_OWNER)  # 版が進み、別のジョブのロックになる

    env.jobs_repository.behavior.before(ops.DELETE, another_job_takes_the_lock, key=LOCK_ID)

    assert make_cancellation(env).cancel(JOB_ID) == Cancelled(JOB_ID)

    lock = env.lock_body()
    assert lock is not None
    assert lock["job_id"] == OTHER_JOB_ID


def test_a_failed_lock_release_after_the_cancel_leaves_a_cancelled_job_and_the_lock() -> None:
    """既知の限界: ロックの削除が失敗すると 503 になる。ジョブは `cancelled`、ロックは残る。

    再試行は 409 `job_already_finished` になり、孤児ロックは管理者の解放か再起動時の回復が消す。
    """
    env = make_env()
    env.seed_job(JOB_ID)
    env.seed_lock(JOB_ID)
    env.jobs_repository.behavior.inject(
        ops.DELETE, StoreUnavailableError("timeout"), key=LOCK_ID, times=None
    )
    cancellation = make_cancellation(env)

    with pytest.raises(StoreUnavailableError):
        cancellation.cancel(JOB_ID)

    assert env.job_body(JOB_ID)["status"] == "cancelled"
    assert env.lock_body() is not None
    assert cancellation.cancel(JOB_ID) == JobAlreadyFinished(JobStatus.CANCELLED)
    assert env.lock_body() is not None


@pytest.mark.parametrize("field", ["status", "job_type"])
def test_a_malformed_job_record_propagates_and_nothing_is_written(field: str) -> None:
    env = make_env()
    env.seed_job(JOB_ID)
    env.seed_lock(JOB_ID)
    env.jobs_repository.seed(JOB_ID, {**env.job_body(JOB_ID), field: "garbage"})
    before = env.job_body(JOB_ID)

    with pytest.raises(StoreUnexpectedResponseError) as raised:
        make_cancellation(env).cancel(JOB_ID)

    assert raised.value.error_type == "malformed_job_record"
    assert "garbage" not in str(raised.value)
    assert env.job_body(JOB_ID) == before
    assert env.lock_body() is not None
    assert env.jobs_repository.write_calls() == []
    assert not env.cancel_requests.is_requested(JOB_ID)


def test_a_lost_update_response_still_cancels_the_job_once() -> None:
    repository = LostResponseRepository()
    env = make_env(repository)
    env.seed_job(JOB_ID)
    env.seed_lock(JOB_ID)
    repository.lose_response_of(ops.REPLACE)

    assert make_cancellation(env).cancel(JOB_ID) == Cancelled(JOB_ID)

    assert env.job_body(JOB_ID)["status"] == "cancelled"
    assert env.lock_body() is None


def test_a_store_failure_that_does_not_end_leaves_the_job_queued() -> None:
    env = make_env()
    env.seed_job(JOB_ID)
    env.seed_lock(JOB_ID)
    env.jobs_repository.behavior.inject(
        ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=None
    )

    with pytest.raises(StoreUnavailableError):
        make_cancellation(env).cancel(JOB_ID)

    assert env.job_body(JOB_ID)["status"] == "queued"
    assert env.lock_body() is not None


# --- 取り消しと実行開始の競合(テスト観点 #25) ---


def test_when_the_runner_wins_the_start_the_cancel_becomes_a_request() -> None:
    env = make_env()
    env.seed_job(JOB_ID)
    env.seed_lock(JOB_ID, lease_expires_at="2026-11-13T00:05:00.000Z")

    def runner_starts_the_job() -> None:
        env.jobs_repository.seed(
            JOB_ID, {**env.job_body(JOB_ID), "status": "running", "started_at": "x"}
        )

    # 取り消しが `queued` を読んだ後、条件付き更新の前に、Job Runner が `running` にする。
    env.jobs_repository.behavior.before(ops.REPLACE, runner_starts_the_job, key=JOB_ID)

    result = make_cancellation(env).cancel(JOB_ID)

    assert result == CancelRequested(JOB_ID)
    assert env.cancel_requests.is_requested(JOB_ID)
    assert env.job_body(JOB_ID)["status"] == "running"  # 取り消しは書き込めていない
    assert env.lock_body() is not None  # 実行中のジョブのロックは解放しない


def test_when_the_cancel_wins_a_later_start_loses() -> None:
    env = make_env()
    record = env.seed_job(JOB_ID)
    env.seed_lock(JOB_ID)

    make_cancellation(env).cancel(JOB_ID)

    # Job Runner が古い版で `running` にしようとしても、条件に負ける(`JobContext` のテストが続き)。
    assert isinstance(env.job_store.update(record, {"status": "running"}), JobSuperseded)
    assert env.job_body(JOB_ID)["status"] == "cancelled"


def test_when_the_job_became_terminal_in_the_race_it_is_reported_as_finished() -> None:
    env = make_env()
    env.seed_job(JOB_ID)
    env.seed_lock(JOB_ID)

    def runner_finishes_the_job() -> None:
        env.jobs_repository.seed(JOB_ID, {**env.job_body(JOB_ID), "status": "failed"})

    env.jobs_repository.behavior.before(ops.REPLACE, runner_finishes_the_job, key=JOB_ID)

    assert make_cancellation(env).cancel(JOB_ID) == JobAlreadyFinished(JobStatus.FAILED)


def test_a_job_that_vanished_in_the_race_is_not_found() -> None:
    env = make_env()
    env.seed_job(JOB_ID)

    def job_vanishes() -> None:
        stored = env.jobs_repository.fetch(JOB_ID)
        assert stored is not None
        env.jobs_repository.delete_if_unchanged(
            JOB_ID, seq_no=stored.seq_no, primary_term=stored.primary_term
        )

    env.jobs_repository.behavior.before(ops.REPLACE, job_vanishes, key=JOB_ID)

    assert make_cancellation(env).cancel(JOB_ID) == JobNotFound()


# --- running: 取り消し要求の伝達(テスト観点 #26) ---


def test_a_running_crawl_gets_a_cancel_request_without_a_record_write() -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    env.seed_lock(JOB_ID, lease_expires_at="2026-11-13T00:05:00.000Z")
    before = env.job_body(JOB_ID)

    result = make_cancellation(env).cancel(JOB_ID)

    assert result == CancelRequested(JOB_ID)
    assert env.cancel_requests.is_requested(JOB_ID)
    assert env.job_body(JOB_ID) == before
    assert env.jobs_repository.write_calls() == []
    assert env.lock_body() is not None


def test_repeated_requests_leave_one_request_and_the_same_result() -> None:
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    cancellation = make_cancellation(env)

    results = [cancellation.cancel(JOB_ID) for _ in range(3)]

    assert results == [CancelRequested(JOB_ID)] * 3
    assert env.cancel_requests.is_requested(JOB_ID)
    env.cancel_requests.clear(JOB_ID)  # 1 回消せば、重ねた要求も消える
    assert not env.cancel_requests.is_requested(JOB_ID)


def test_a_cancelled_job_is_reported_as_finished_on_a_repeated_request() -> None:
    env = make_env()
    env.seed_job(JOB_ID)
    cancellation = make_cancellation(env)
    cancellation.cancel(JOB_ID)

    assert cancellation.cancel(JOB_ID) == JobAlreadyFinished(JobStatus.CANCELLED)


def test_a_request_recorded_while_the_job_finishes_is_not_left_behind() -> None:
    """要求を記録する間にジョブが終端になったら、誰も消さない要求を残さない。"""
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING)

    def job_finishes() -> None:
        env.jobs_repository.seed(JOB_ID, {**env.job_body(JOB_ID), "status": "succeeded"})

    # 1 回目の読み取り(判定)は通し、要求を記録した後の読み直しの前に、ジョブが終わる。
    behavior = env.jobs_repository.behavior
    behavior.before(ops.FETCH, lambda: None, key=JOB_ID)
    behavior.before(ops.FETCH, job_finishes, key=JOB_ID)

    result = make_cancellation(env).cancel(JOB_ID)

    assert result == JobAlreadyFinished(JobStatus.SUCCEEDED)
    assert not env.cancel_requests.is_requested(JOB_ID)


def test_the_registry_is_empty_after_a_restart() -> None:  # テスト観点 #27 の一部
    env = make_env()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    make_cancellation(env).cancel(JOB_ID)
    assert env.cancel_requests.is_requested(JOB_ID)

    restarted = make_env(env.jobs_repository)  # プロセスの再起動: 新しいレジストリ

    assert not restarted.cancel_requests.is_requested(JOB_ID)
