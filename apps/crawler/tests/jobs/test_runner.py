"""Job Runner(module 4.4・5.2・2.2。architecture 4.5・5.3・5.5・5.7)。

対応するテスト観点は #13・#14・#25・#26・#28・#32・#33。実行対象は偽物(関数)で、`crawl`・
`source_delete` は使わない。ハートビートは本物を `ManualWaiter` で動かす(スレッドは待ちに入った
まま。時間は固定時計)。スレッドのテストは `Event` と上限つきの待ちで書く。
"""

import logging
import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.jobs import (
    CancellationRequested,
    FailureReason,
    JobCancellation,
    JobContext,
    JobExecutor,
    JobRecord,
    JobRunner,
    JobsSettings,
    JobStatus,
    JobType,
    LockRelease,
    OwnershipLost,
    RunnerWakeup,
    StartupRecovery,
)
from loreley_crawler.jobs.locks import Heartbeat, HeartbeatSettings
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW
from tests.jobs.locks.support import ManualWaiter, wait_for_heartbeat_thread_to_finish
from tests.jobs.support import (
    JOB_ID,
    LOCK_ID,
    NO_WAIT_RETRIER,
    OTHER_JOB_ID,
    OTHER_OWNER,
    OWNER,
    SOURCE_ID,
    WAIT_TIMEOUT_SECONDS,
    JobsEnv,
    make_env,
)

HEARTBEAT_SETTINGS = HeartbeatSettings(
    lease_seconds=300.0,
    interval_seconds=100.0,
    retry_interval_seconds=10.0,
    stop_timeout_seconds=WAIT_TIMEOUT_SECONDS,
)


@dataclass
class RunnerFixture:
    env: JobsEnv
    runner: JobRunner
    heartbeats: list[Heartbeat]
    waiters: list[ManualWaiter]
    calls: list[tuple[JobType, JobRecord]]


def succeed(record: JobRecord, context: JobContext) -> None:
    context.start_running()
    context.finish(JobStatus.SUCCEEDED)


def make_runner(
    env: JobsEnv,
    *,
    crawl: JobExecutor = succeed,
    source_delete: JobExecutor = succeed,
    heartbeat_settings: HeartbeatSettings = HEARTBEAT_SETTINGS,
    scan_interval_seconds: float = 5.0,
    heartbeat_type: type[Heartbeat] = Heartbeat,
) -> RunnerFixture:
    heartbeats: list[Heartbeat] = []
    waiters: list[ManualWaiter] = []
    calls: list[tuple[JobType, JobRecord]] = []

    def recording(job_type: JobType, executor: JobExecutor) -> JobExecutor:
        def run(record: JobRecord, context: JobContext) -> None:
            calls.append((job_type, record))
            executor(record, context)

        return run

    def new_heartbeat() -> Heartbeat:
        waiter = ManualWaiter()
        heartbeat = heartbeat_type(env.lock_store, env.clock, heartbeat_settings, waiter=waiter)
        heartbeats.append(heartbeat)
        waiters.append(waiter)
        return heartbeat

    runner = JobRunner(
        settings=JobsSettings(
            owner=OWNER,
            heartbeat=heartbeat_settings,
            runner_scan_interval_seconds=scan_interval_seconds,
        ),
        job_store=env.job_store,
        lock_store=env.lock_store,
        heartbeat_factory=new_heartbeat,
        executors={
            JobType.CRAWL: recording(JobType.CRAWL, crawl),
            JobType.SOURCE_DELETE: recording(JobType.SOURCE_DELETE, source_delete),
        },
        cancel_requests=env.cancel_requests,
        wakeup=env.wakeup,
        read_maintenance_flag=env.read_maintenance_flag,
        clock=env.clock,
        retrier=NO_WAIT_RETRIER,
    )
    return RunnerFixture(env, runner, heartbeats, waiters, calls)


def seed_queued(
    env: JobsEnv, job_id: str = JOB_ID, source_id: str = SOURCE_ID, **kwargs: Any
) -> JobRecord:
    # ロックを先に置く(Runner のスレッドが動いていても、ジョブが見えたときにはロックがある)。
    env.seed_lock(job_id, source_id=source_id)
    return env.seed_job(job_id, source_id=source_id, **kwargs)


def lock_delete_calls(env: JobsEnv) -> int:
    calls = env.jobs_repository.behavior.calls_of(ops.DELETE)
    return len([call for call in calls if call.key == LOCK_ID])


# --- 取り出しの順序と実行 ---


def test_an_idle_runner_runs_nothing() -> None:
    fixture = make_runner(make_env())

    assert fixture.runner.run_next() is False
    assert fixture.calls == []


def test_a_queued_job_is_executed_and_its_lock_is_released() -> None:
    env = make_env()
    seed_queued(env)
    fixture = make_runner(env)

    assert fixture.runner.run_next() is True

    [(job_type, record)] = fixture.calls
    assert (job_type, record.job_id, record.status) == (JobType.CRAWL, JOB_ID, JobStatus.QUEUED)
    assert env.job_body(JOB_ID)["status"] == "succeeded"
    assert env.lock_body() is None
    assert lock_delete_calls(env) == 1  # 解放は 1 回
    wait_for_heartbeat_thread_to_finish()


def test_the_lease_is_set_and_the_heartbeat_runs_while_the_executor_works() -> None:
    env = make_env()
    seed_queued(env)
    seen: dict[str, object] = {}

    def inspect(record: JobRecord, context: JobContext) -> None:
        lock = env.lock_body()
        assert lock is not None
        seen["lease"] = lock["lease_expires_at"]
        seen["heartbeat_alive"] = fixture.heartbeats[0].is_owned()
        seen["job_status_before_start"] = env.job_body(JOB_ID)["status"]
        succeed(record, context)

    fixture = make_runner(env, crawl=inspect)

    fixture.runner.run_next()

    assert seen == {
        "lease": "2026-11-13T00:05:00.000Z",  # 現在時刻 + リース時間(300 秒)
        "heartbeat_alive": True,
        "job_status_before_start": "queued",  # `running` にするのは実行対象(`JobContext` 経由)
    }


def test_jobs_run_one_at_a_time_in_queued_at_order() -> None:
    env = make_env()
    # `job_id` の辞書順と `queued_at` の順が逆になるようにする。
    seed_queued(env, "job-x", "source-x", queued_at=DEFAULT_NOW + timedelta(seconds=2))
    seed_queued(env, "job-z", "source-z", queued_at=DEFAULT_NOW)
    seed_queued(env, "job-y", "source-y", queued_at=DEFAULT_NOW + timedelta(seconds=1))
    fixture = make_runner(env)

    results = [fixture.runner.run_next() for _ in range(4)]

    assert results == [True, True, True, False]
    assert [record.job_id for _, record in fixture.calls] == ["job-z", "job-y", "job-x"]


def test_jobs_queued_at_the_same_instant_run_in_job_id_order() -> None:
    env = make_env()
    seed_queued(env, "job-2", "source-2")
    seed_queued(env, "job-1", "source-1")
    fixture = make_runner(env)

    fixture.runner.run_next()

    assert [record.job_id for _, record in fixture.calls] == ["job-1"]


def test_only_queued_jobs_of_this_owner_run() -> None:
    env = make_env()
    seed_queued(env, "job-other", "source-other", owner=OTHER_OWNER)
    env.seed_job("job-done", source_id="source-done", status=JobStatus.SUCCEEDED)
    env.seed_job("job-running", source_id="source-running", status=JobStatus.RUNNING)
    fixture = make_runner(env)

    assert fixture.runner.run_next() is False
    assert fixture.calls == []


def test_the_executor_is_chosen_by_job_type() -> None:
    env = make_env()
    seed_queued(env, "job-a", "source-a", job_type=JobType.SOURCE_DELETE)
    seed_queued(
        env, "job-b", "source-b", job_type=JobType.CRAWL, queued_at=DEFAULT_NOW + timedelta(1)
    )
    fixture = make_runner(env)

    fixture.runner.run_next()
    fixture.runner.run_next()

    assert [(job_type, record.job_id) for job_type, record in fixture.calls] == [
        (JobType.SOURCE_DELETE, "job-a"),
        (JobType.CRAWL, "job-b"),
    ]


def test_an_executor_is_required_for_every_job_type() -> None:
    env = make_env()
    fixture = make_runner(env)

    with pytest.raises(ValueError):
        JobRunner(
            settings=JobsSettings(owner=OWNER),
            job_store=env.job_store,
            lock_store=env.lock_store,
            heartbeat_factory=lambda: fixture.heartbeats[0],
            executors={JobType.CRAWL: succeed},
            cancel_requests=env.cancel_requests,
            wakeup=env.wakeup,
            read_maintenance_flag=env.read_maintenance_flag,
            clock=env.clock,
            retrier=NO_WAIT_RETRIER,
        )


# --- 解放は、実行対象の終わり方を問わず 1 回(architecture 5.5) ---


def test_the_lock_is_released_once_after_an_executor_that_raised() -> None:
    env = make_env()
    seed_queued(env)

    def raises_after_starting(record: JobRecord, context: JobContext) -> None:
        context.start_running()
        raise RuntimeError("SECRET-detail-of-a-bug")

    fixture = make_runner(env, crawl=raises_after_starting)

    fixture.runner.run_next()

    body = env.job_body(JOB_ID)
    assert (body["status"], body["failure_reason"]) == ("failed", "internal_error")
    assert env.lock_body() is None
    assert lock_delete_calls(env) == 1
    wait_for_heartbeat_thread_to_finish()


def test_a_store_failure_that_escapes_the_executor_is_failed_as_store_unavailable() -> None:
    env = make_env()
    seed_queued(env)

    def store_goes_down(record: JobRecord, context: JobContext) -> None:
        context.start_running()
        raise StoreUnavailableError("timeout")

    fixture = make_runner(env, crawl=store_goes_down)

    fixture.runner.run_next()

    assert env.job_body(JOB_ID)["failure_reason"] == "store_unavailable"  # テスト観点 #33
    assert env.lock_body() is None


def test_an_unexpected_store_response_is_failed_as_internal_error_not_store_unavailable() -> None:
    """Crawler 側の不具合の疑い(リトライで直らない)なので、`store_unavailable` にしない。"""
    env = make_env()
    seed_queued(env)

    def store_misbehaves(record: JobRecord, context: JobContext) -> None:
        context.start_running()
        raise StoreUnexpectedResponseError("non_unique_sort")

    fixture = make_runner(env, crawl=store_misbehaves)

    fixture.runner.run_next()

    body = env.job_body(JOB_ID)
    assert (body["status"], body["failure_reason"]) == ("failed", "internal_error")
    assert env.lock_body() is None


@pytest.mark.parametrize(
    ("final_status", "failure_reason"),
    [
        (JobStatus.SUCCEEDED, None),
        (JobStatus.PARTIALLY_SUCCEEDED, None),
        (JobStatus.CANCELLED, None),
        (JobStatus.FAILED, FailureReason.CONFIG_INVALID),
    ],
)
def test_an_exception_after_the_final_state_does_not_change_it_and_the_lock_is_released(
    final_status: JobStatus,
    failure_reason: FailureReason | None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """最終状態を記録した後の例外で、最後の手段の `failed` が記録済みの状態を上書きしない。"""
    env = make_env()
    seed_queued(env)

    def finishes_then_raises(record: JobRecord, context: JobContext) -> None:
        context.start_running()
        context.finish(final_status, failure_reason=failure_reason)
        raise RuntimeError("SECRET-late-bug")

    fixture = make_runner(env, crawl=finishes_then_raises)

    with caplog.at_level(logging.WARNING):
        assert fixture.runner.run_next() is True

    body = env.job_body(JOB_ID)
    assert body["status"] == final_status.value
    assert body.get("failure_reason") == (failure_reason.value if failure_reason else None)
    assert env.lock_body() is None  # 最終状態は記録できているので、解放する
    assert lock_delete_calls(env) == 1
    assert "RuntimeError" in caplog.text  # 例外の種類だけをログに出す
    assert "SECRET-late-bug" not in caplog.text
    wait_for_heartbeat_thread_to_finish()


def test_an_executor_that_returns_without_a_final_state_is_failed_as_internal_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    seed_queued(env)

    def forgets_the_final_state(record: JobRecord, context: JobContext) -> None:
        context.start_running()

    fixture = make_runner(env, crawl=forgets_the_final_state)

    with caplog.at_level(logging.WARNING):
        fixture.runner.run_next()

    assert env.job_body(JOB_ID)["failure_reason"] == "internal_error"
    assert env.lock_body() is None
    assert "without recording a final state" in caplog.text


def test_an_executor_that_failed_before_starting_gets_a_failed_job_from_the_queued_state() -> None:
    env = make_env()
    seed_queued(env)

    def raises_immediately(record: JobRecord, context: JobContext) -> None:
        raise ValueError

    fixture = make_runner(env, crawl=raises_immediately)

    fixture.runner.run_next()

    body = env.job_body(JOB_ID)
    assert (body["status"], body["failure_reason"]) == ("failed", "internal_error")
    assert env.lock_body() is None


def test_the_unexpected_error_is_logged_by_type_only(caplog: pytest.LogCaptureFixture) -> None:
    env = make_env()
    seed_queued(env)

    def raises(record: JobRecord, context: JobContext) -> None:
        context.start_running()
        raise RuntimeError("SECRET-detail-of-a-bug")

    fixture = make_runner(env, crawl=raises)

    with caplog.at_level(logging.DEBUG):
        fixture.runner.run_next()

    assert "RuntimeError" in caplog.text
    assert "SECRET-detail-of-a-bug" not in caplog.text
    assert "SECRET-detail-of-a-bug" not in str(env.job_body(JOB_ID))


def test_the_heartbeat_is_stopped_before_the_lock_is_deleted() -> None:
    env = make_env()
    seed_queued(env)
    events: list[str] = []

    class ObservedHeartbeat(Heartbeat):
        def stop(self, *, timeout_seconds: float | None = None) -> bool:
            events.append("heartbeat stopped")
            return super().stop(timeout_seconds=timeout_seconds)

    # 実行対象が終わった後(解放のとき)の、ロック文書の削除の直前に記録する。
    def executor(record: JobRecord, context: JobContext) -> None:
        succeed(record, context)
        env.jobs_repository.behavior.before(
            ops.DELETE, lambda: events.append("lock deleted"), key=LOCK_ID
        )

    fixture = make_runner(env, crawl=executor, heartbeat_type=ObservedHeartbeat)

    fixture.runner.run_next()

    assert events == ["heartbeat stopped", "lock deleted"]


# --- 取り消しに負けた実行開始(テスト観点 #25) ---


def test_a_start_that_lost_to_a_cancel_stops_without_running_and_releases_the_lock() -> None:
    env = make_env()
    seed_queued(env)

    def cancel_wins() -> None:
        JobCancellation(
            job_store=env.job_store,
            lock_store=env.lock_store,
            cancel_requests=env.cancel_requests,
            clock=env.clock,
            retrier=NO_WAIT_RETRIER,
        ).cancel(JOB_ID)

    reached_after_start: list[str] = []

    def executor(record: JobRecord, context: JobContext) -> None:
        # 実行対象が `running` にしようとする直前に、取り消しが先に条件付き更新に勝つ。
        env.jobs_repository.behavior.before(ops.REPLACE, cancel_wins, key=JOB_ID)
        context.start_running()
        reached_after_start.append("running")

    fixture = make_runner(env, crawl=executor)

    assert fixture.runner.run_next() is True

    assert reached_after_start == []
    body = env.job_body(JOB_ID)
    assert body["status"] == "cancelled"  # 取り消しが有効。`failed` などで上書きしない
    assert "failure_reason" not in body
    assert env.lock_body() is None
    wait_for_heartbeat_thread_to_finish()


def test_a_start_that_lost_to_a_cancel_releases_the_lock_even_if_the_cancel_did_not() -> None:
    """取り消し側がロックを消す前に、Job Runner が負けを知った場合は、Job Runner が解放する。"""
    env = make_env()
    seed_queued(env)

    def executor(record: JobRecord, context: JobContext) -> None:
        env.jobs_repository.seed(
            JOB_ID, {**env.job_body(JOB_ID), "status": "cancelled", "finished_at": "x"}
        )
        context.start_running()

    fixture = make_runner(env, crawl=executor)

    fixture.runner.run_next()

    assert env.job_body(JOB_ID)["status"] == "cancelled"
    assert env.lock_body() is None


def test_when_the_runner_wins_a_later_cancel_request_is_seen_at_a_checkpoint() -> None:
    """Job Runner が先に `running` にした場合、取り消しは要求として伝わる(観点 #25・#26)。"""
    env = make_env()
    seed_queued(env)
    seen: dict[str, object] = {}

    def executor(record: JobRecord, context: JobContext) -> None:
        context.start_running()
        result = JobCancellation(
            job_store=env.job_store,
            lock_store=env.lock_store,
            cancel_requests=env.cancel_requests,
            clock=env.clock,
            retrier=NO_WAIT_RETRIER,
        ).cancel(JOB_ID)
        seen["cancel_result"] = type(result).__name__
        try:
            context.check()
        except CancellationRequested:
            seen["checkpoint"] = "cancellation requested"
            context.finish(JobStatus.CANCELLED)

    fixture = make_runner(env, crawl=executor)

    fixture.runner.run_next()

    assert seen == {"cancel_result": "CancelRequested", "checkpoint": "cancellation requested"}
    assert env.job_body(JOB_ID)["status"] == "cancelled"
    assert not env.cancel_requests.is_requested(JOB_ID)  # 終端の後、要求は消える
    assert env.lock_body() is None


def test_a_cancel_request_is_cleared_even_when_the_executor_never_checks_it() -> None:
    env = make_env()
    seed_queued(env)

    def executor(record: JobRecord, context: JobContext) -> None:
        env.cancel_requests.request(JOB_ID)
        raise RuntimeError

    fixture = make_runner(env, crawl=executor)

    fixture.runner.run_next()

    assert not env.cancel_requests.is_requested(JOB_ID)


# --- リースを設定できないジョブ ---


def test_a_queued_job_whose_lock_is_missing_is_failed_without_running(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    env.seed_job(JOB_ID)  # ロックなし
    fixture = make_runner(env)

    with caplog.at_level(logging.WARNING):
        assert fixture.runner.run_next() is True

    assert fixture.calls == []
    body = env.job_body(JOB_ID)
    assert (body["status"], body["failure_reason"]) == ("failed", "lock_lost")
    assert fixture.heartbeats == []  # ハートビートも始めない
    assert "lost its lock" in caplog.text


def test_a_queued_job_whose_lock_belongs_to_another_job_is_failed_and_the_lock_is_left() -> None:
    env = make_env()
    env.seed_job(JOB_ID)
    env.seed_lock(OTHER_JOB_ID, owner=OTHER_OWNER)
    fixture = make_runner(env)

    fixture.runner.run_next()

    assert fixture.calls == []
    assert env.job_body(JOB_ID)["failure_reason"] == "lock_lost"
    lock = env.lock_body()
    assert lock is not None
    assert lock["job_id"] == OTHER_JOB_ID


def test_a_lock_taken_over_while_setting_the_lease_fails_the_job() -> None:
    env = make_env()
    seed_queued(env)
    env.jobs_repository.behavior.before(
        ops.REPLACE,
        lambda: env.seed_lock(OTHER_JOB_ID, owner=OTHER_OWNER),
        key=LOCK_ID,
    )
    fixture = make_runner(env)

    fixture.runner.run_next()

    assert fixture.calls == []
    assert env.job_body(JOB_ID)["failure_reason"] == "lock_lost"
    lock = env.lock_body()
    assert lock is not None
    assert lock["job_id"] == OTHER_JOB_ID


def test_a_job_cancelled_after_it_was_picked_is_not_run_nor_overwritten() -> None:
    env = make_env()
    seed_queued(env)

    def cancel_after_pick() -> None:
        JobCancellation(
            job_store=env.job_store,
            lock_store=env.lock_store,
            cancel_requests=env.cancel_requests,
            clock=env.clock,
            retrier=NO_WAIT_RETRIER,
        ).cancel(JOB_ID)

    env.jobs_repository.behavior.before(ops.FETCH, cancel_after_pick, key=LOCK_ID)
    fixture = make_runner(env)

    fixture.runner.run_next()

    assert fixture.calls == []
    assert env.job_body(JOB_ID)["status"] == "cancelled"
    assert "failure_reason" not in env.job_body(JOB_ID)


# --- 解放しないロック(テスト観点 #32) ---


def test_the_lock_is_not_deleted_when_the_ownership_loss_was_recorded() -> None:
    env = make_env()
    seed_queued(env)

    def loses_ownership(record: JobRecord, context: JobContext) -> None:
        context.start_running()
        context.record_lock_not_owned()
        context.finish(JobStatus.FAILED, failure_reason=FailureReason.LOCK_LOST)

    fixture = make_runner(env, crawl=loses_ownership)

    fixture.runner.run_next()

    body = env.job_body(JOB_ID)
    assert (body["status"], body["failure_reason"]) == ("failed", "lock_lost")
    lock = env.lock_body()
    assert lock is not None  # 自分の `owner`・`job_id` のままでも削除しない
    assert (lock["owner"], lock["job_id"]) == (OWNER, JOB_ID)
    assert lock_delete_calls(env) == 0
    wait_for_heartbeat_thread_to_finish()


def test_the_lock_is_not_deleted_when_the_heartbeat_recorded_the_loss() -> None:
    env = make_env()
    seed_queued(env)

    def heartbeat_loses_the_lock(record: JobRecord, context: JobContext) -> None:
        context.start_running()
        fixture.heartbeats[0].record_loss("lock_taken_over")
        with pytest.raises(OwnershipLost):
            context.check()
        context.finish(JobStatus.FAILED, failure_reason=FailureReason.LOCK_LOST)

    fixture = make_runner(env, crawl=heartbeat_loses_the_lock)

    fixture.runner.run_next()

    assert env.lock_body() is not None
    assert lock_delete_calls(env) == 0


def test_the_lock_is_not_deleted_when_the_heartbeat_does_not_stop_in_time(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """停止の待ちの上限を超えたら、喪失として扱い、ロック文書は削除せずに終える。"""
    env = make_env()
    seed_queued(env)
    in_update = threading.Event()
    gate = threading.Event()

    def stuck_update() -> None:
        in_update.set()
        gate.wait(WAIT_TIMEOUT_SECONDS)

    def executor(record: JobRecord, context: JobContext) -> None:
        succeed(record, context)
        # ハートビートの更新が、Store 層の呼び出しの中で止まる。
        env.jobs_repository.behavior.before(ops.REPLACE, stuck_update, key=LOCK_ID)
        fixture.waiters[0].release_tick()
        assert in_update.wait(WAIT_TIMEOUT_SECONDS)

    stuck = HeartbeatSettings(300.0, 100.0, 10.0, stop_timeout_seconds=0.05)
    fixture = make_runner(env, crawl=executor, heartbeat_settings=stuck)

    try:
        with caplog.at_level(logging.WARNING):
            fixture.runner.run_next()

        assert env.job_body(JOB_ID)["status"] == "succeeded"
        assert fixture.heartbeats[0].lost_reason == "stop_timeout"
        assert env.lock_body() is not None
        assert lock_delete_calls(env) == 0
        assert "the lock is kept" in caplog.text
    finally:
        gate.set()
        wait_for_heartbeat_thread_to_finish()


def test_the_lock_is_kept_when_the_final_state_could_not_be_recorded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    seed_queued(env)

    def store_goes_down_for_good(record: JobRecord, context: JobContext) -> None:
        context.start_running()
        env.jobs_repository.behavior.inject(
            ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=None
        )
        raise RuntimeError

    fixture = make_runner(env, crawl=store_goes_down_for_good)

    with caplog.at_level(logging.WARNING):
        assert fixture.runner.run_next() is False  # 終端にできなかった。待たずに繰り返さない

    assert env.job_body(JOB_ID)["status"] == "running"  # 記録できなかった
    assert env.lock_body() is not None  # `running` のジョブのロックは消さない
    assert "could not record the last-resort failure" in caplog.text
    wait_for_heartbeat_thread_to_finish()  # ハートビートは止める


def test_a_cancel_request_is_cleared_even_when_no_final_state_could_be_recorded() -> None:
    env = make_env()
    seed_queued(env)

    def store_goes_down_after_a_request(record: JobRecord, context: JobContext) -> None:
        context.start_running()
        env.cancel_requests.request(JOB_ID)
        env.jobs_repository.behavior.inject(
            ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=None
        )
        raise RuntimeError

    fixture = make_runner(env, crawl=store_goes_down_after_a_request)

    fixture.runner.run_next()

    assert env.job_body(JOB_ID)["status"] == "running"  # 記録できなかった
    assert not env.cancel_requests.is_requested(JOB_ID)  # 要求だけは、メモリに残さない


def test_a_transient_failure_of_the_release_is_retried() -> None:
    env = make_env()
    seed_queued(env)

    def executor(record: JobRecord, context: JobContext) -> None:
        succeed(record, context)
        env.jobs_repository.behavior.inject(
            ops.DELETE, StoreUnavailableError("timeout"), key=LOCK_ID, times=2
        )

    fixture = make_runner(env, crawl=executor)

    fixture.runner.run_next()

    assert env.lock_body() is None


def test_a_transient_failure_of_the_queue_scan_is_retried_within_one_run() -> None:
    env = make_env()
    seed_queued(env)
    env.jobs_repository.behavior.inject(ops.LIST, StoreUnavailableError("timeout"), times=2)
    fixture = make_runner(env)

    assert fixture.runner.run_next() is True

    assert env.job_body(JOB_ID)["status"] == "succeeded"


def test_a_failed_release_leaves_an_orphan_lock_and_does_not_raise(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    seed_queued(env)

    def executor(record: JobRecord, context: JobContext) -> None:
        succeed(record, context)
        env.jobs_repository.behavior.inject(
            ops.DELETE, StoreUnavailableError("timeout"), key=LOCK_ID, times=None
        )

    fixture = make_runner(env, crawl=executor)

    with caplog.at_level(logging.WARNING):
        assert fixture.runner.run_next() is True

    assert env.job_body(JOB_ID)["status"] == "succeeded"
    assert env.lock_body() is not None
    assert "orphan lock remains" in caplog.text


# --- ロック解放(管理者)と Job Runner の競合(テスト観点 #28) ---


def test_after_the_admin_released_the_lock_the_runner_stops_and_leaves_the_new_lock_alone() -> None:
    env = make_env()
    seed_queued(env)
    seen: dict[str, object] = {}

    def executor(record: JobRecord, context: JobContext) -> None:
        context.start_running()
        # リースが切れた(ハートビートが止まった)ところに、管理者の解放が入る。
        env.clock.advance(seconds=HEARTBEAT_SETTINGS.lease_seconds)
        released = LockRelease(
            settings=env.settings,
            job_store=env.job_store,
            lock_store=env.lock_store,
            clock=env.clock,
            retrier=NO_WAIT_RETRIER,
        ).release(SOURCE_ID)
        seen["released"] = type(released).__name__
        # 解放の直後に、新しい受付がロックを取る。
        env.seed_lock(OTHER_JOB_ID, owner=OTHER_OWNER, acquired_at=env.clock.now())
        try:
            context.update({"registration": {"partial": True}})
        except OwnershipLost:
            seen["update"] = "ownership lost"
        context.finish(JobStatus.SUCCEEDED)  # 解放側の `failed` を上書きしない

    fixture = make_runner(env, crawl=executor)

    fixture.runner.run_next()

    assert seen == {"released": "LockReleased", "update": "ownership lost"}
    body = env.job_body(JOB_ID)
    assert (body["status"], body["failure_reason"]) == ("failed", "lock_released")
    assert "registration" not in body
    lock = env.lock_body()
    assert lock is not None
    assert lock["job_id"] == OTHER_JOB_ID  # 他のジョブのロックを消さない
    assert fixture.heartbeats[0].lost_reason == "job_record_superseded"


def test_the_runner_never_deletes_a_lock_that_became_another_jobs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """喪失を記録していなくても、解放は版条件つきで、他のジョブのロックは消さない。"""
    env = make_env()
    seed_queued(env)

    def executor(record: JobRecord, context: JobContext) -> None:
        succeed(record, context)
        env.seed_lock(OTHER_JOB_ID, owner=OTHER_OWNER)

    fixture = make_runner(env, crawl=executor)

    with caplog.at_level(logging.WARNING):
        fixture.runner.run_next()

    lock = env.lock_body()
    assert lock is not None
    assert lock["job_id"] == OTHER_JOB_ID
    assert "the lock was not released" in caplog.text
    assert "lock_taken_over" in caplog.text  # 理由(固定の名前)


# --- ホットループの防止・形式不正の記録・例外の経路 ---


class StoppingWakeup(RunnerWakeup):
    """待ちを記録して、停止を要求する(ループを同期的に 1 周で止める)。"""

    def __init__(self) -> None:
        super().__init__()
        self.waits: list[float] = []
        self.runner: JobRunner | None = None

    def wait(self, timeout_seconds: float) -> bool:
        self.waits.append(timeout_seconds)
        assert self.runner is not None
        self.runner.request_stop()
        return False


def test_a_job_that_cannot_be_ended_waits_for_the_scan_interval_instead_of_spinning() -> None:
    env = make_env()
    wakeup = StoppingWakeup()
    env.wakeup = wakeup
    seed_queued(env)
    calls: list[str] = []

    def fails_before_starting_while_the_store_is_down(
        record: JobRecord, context: JobContext
    ) -> None:
        calls.append(record.job_id)
        if len(calls) > 1:
            fixture.runner.request_stop()  # 待たずに繰り返したら、ここで止めて失敗にする
        env.jobs_repository.behavior.inject(
            ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=None
        )
        raise RuntimeError

    fixture = make_runner(
        env, crawl=fails_before_starting_while_the_store_is_down, scan_interval_seconds=7.0
    )
    wakeup.runner = fixture.runner

    fixture.runner.run_until_stopped()

    assert calls == [JOB_ID]  # 1 回だけ試み、走査間隔だけ待つ
    assert wakeup.waits == [7.0]
    assert env.job_body(JOB_ID)["status"] == "queued"  # 終端にできなかった


def test_a_malformed_queued_record_is_logged_with_its_job_id_and_the_loop_goes_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """形式不正の `queued` が先頭にあっても、Runner は落ちず、警告して走査間隔だけ待つ(0011 §7)。"""
    env = make_env()
    wakeup = StoppingWakeup()
    env.wakeup = wakeup
    seed_queued(env, "job-bad", "source-bad")
    env.jobs_repository.seed("job-bad", {**env.job_body("job-bad"), "job_type": "garbage"})
    fixture = make_runner(env)
    wakeup.runner = fixture.runner

    with caplog.at_level(logging.WARNING):
        fixture.runner.run_until_stopped()

    assert fixture.calls == []
    assert wakeup.waits == [5.0]
    assert "failed to run a job: job_id=job-bad" in caplog.text
    assert "StoreUnexpectedResponseError" in caplog.text
    assert "garbage" not in caplog.text
    assert env.job_body("job-bad")["status"] == "queued"


@pytest.mark.parametrize("exit_type", [SystemExit, KeyboardInterrupt])
def test_the_heartbeat_is_stopped_even_when_the_executor_exits_the_thread(
    exit_type: type[BaseException],
) -> None:
    env = make_env()
    seed_queued(env)

    def exits(record: JobRecord, context: JobContext) -> None:
        context.start_running()
        raise exit_type

    fixture = make_runner(env, crawl=exits)

    with pytest.raises(exit_type):
        fixture.runner.run_next()

    wait_for_heartbeat_thread_to_finish()  # スレッドが残らない
    assert env.lock_body() is not None  # 最終状態を記録していないので、ロックは消さない
    assert not env.cancel_requests.is_requested(JOB_ID)
    assert env.job_body(JOB_ID)["status"] == "running"


def test_a_heartbeat_that_fails_to_start_leaves_the_job_queued_and_the_lock_kept(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    seed_queued(env)
    stopped: list[bool] = []

    class FailingStartHeartbeat(Heartbeat):
        def start(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("cannot start a thread")

        def stop(self, *, timeout_seconds: float | None = None) -> bool:
            stopped.append(True)
            return super().stop(timeout_seconds=timeout_seconds)

    fixture = make_runner(env, heartbeat_type=FailingStartHeartbeat)

    with caplog.at_level(logging.WARNING):
        assert fixture.runner.run_next() is False

    assert fixture.calls == []  # 実行対象は呼ばれない
    assert stopped == [True]
    assert env.job_body(JOB_ID)["status"] == "queued"
    assert env.lock_body() is not None
    assert "RuntimeError" in caplog.text


def test_a_failure_to_set_the_lease_for_good_is_logged_and_does_not_spin(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    seed_queued(env)
    env.jobs_repository.behavior.inject(
        ops.REPLACE, StoreUnavailableError("timeout"), key=LOCK_ID, times=None
    )
    fixture = make_runner(env)

    with caplog.at_level(logging.WARNING):
        assert fixture.runner.run_next() is False

    assert fixture.calls == []
    assert env.job_body(JOB_ID)["status"] == "queued"
    assert f"failed to run a job: job_id={JOB_ID}" in caplog.text
    assert "StoreUnavailableError" in caplog.text


def test_a_store_failure_in_an_update_ends_as_failed_store_unavailable() -> None:
    """テスト観点 #33 の一気通貫: 更新の例外が Runner まで伝わり、最後の手段が記録する。"""
    env = make_env()
    seed_queued(env)
    seen: list[str] = []

    def executor(record: JobRecord, context: JobContext) -> None:
        context.start_running()
        env.jobs_repository.behavior.inject(
            ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=3
        )
        try:
            context.update({"registration": {"partial": True}})
        except StoreUnavailableError:
            seen.append("raised")
            raise

    fixture = make_runner(env, crawl=executor)

    assert fixture.runner.run_next() is True

    assert seen == ["raised"]  # リトライ(3 回)を尽くして、Runner まで伝わった
    body = env.job_body(JOB_ID)
    assert (body["status"], body["failure_reason"]) == ("failed", "store_unavailable")
    assert "registration" not in body
    assert env.lock_body() is None


def test_a_queued_job_with_a_stale_lease_runs_after_the_startup_recovery() -> None:
    """起動時の回復は `queued` をロックごと残し、Job Runner が古いリースを設定し直して実行する。"""
    env = make_env()
    env.seed_lock(JOB_ID, lease_expires_at="2026-11-12T00:00:00.000Z")  # 前のプロセスの古い期限
    env.seed_job(JOB_ID)
    leases: list[object] = []

    def executor(record: JobRecord, context: JobContext) -> None:
        lock = env.lock_body()
        assert lock is not None
        leases.append(lock["lease_expires_at"])
        succeed(record, context)

    fixture = make_runner(env, crawl=executor)

    report = StartupRecovery(
        settings=env.settings,
        job_store=env.job_store,
        lock_store=env.lock_store,
        clock=env.clock,
        retrier=NO_WAIT_RETRIER,
    ).run()
    assert report.kept_lock_source_ids == (SOURCE_ID,)
    assert fixture.runner.run_next() is True

    assert leases == ["2026-11-13T00:05:00.000Z"]  # 再設定された
    assert env.job_body(JOB_ID)["status"] == "succeeded"
    assert env.lock_body() is None


# --- スレッド: 起床通知と走査間隔 ---


def start_runner_thread(fixture: RunnerFixture) -> None:
    fixture.runner.start()


def stop_runner_thread(fixture: RunnerFixture) -> None:
    fixture.runner.request_stop()
    assert fixture.runner.join(WAIT_TIMEOUT_SECONDS)


def test_a_notification_wakes_an_idle_runner_without_waiting_for_the_scan_interval() -> None:
    env = make_env()
    executed = threading.Event()

    def executor(record: JobRecord, context: JobContext) -> None:
        succeed(record, context)
        executed.set()

    # 走査間隔は十分に長い。通知だけで動くことを確かめる。
    fixture = make_runner(env, crawl=executor, scan_interval_seconds=3_600.0)
    start_runner_thread(fixture)
    try:
        seed_queued(env)
        env.wakeup.notify()

        assert executed.wait(WAIT_TIMEOUT_SECONDS)
    finally:
        stop_runner_thread(fixture)
    wait_for_heartbeat_thread_to_finish()


def test_the_scan_interval_finds_a_job_even_if_the_notification_was_missed() -> None:
    env = make_env()
    executed = threading.Event()

    def executor(record: JobRecord, context: JobContext) -> None:
        succeed(record, context)
        executed.set()

    fixture = make_runner(env, crawl=executor, scan_interval_seconds=0.01)
    start_runner_thread(fixture)
    try:
        seed_queued(env)  # 通知しない

        assert executed.wait(WAIT_TIMEOUT_SECONDS)
    finally:
        stop_runner_thread(fixture)
    wait_for_heartbeat_thread_to_finish()


def test_the_runner_drains_every_queued_job_before_waiting() -> None:
    env = make_env()
    done: list[str] = []
    all_done = threading.Event()

    def executor(record: JobRecord, context: JobContext) -> None:
        succeed(record, context)
        done.append(record.job_id)
        if len(done) == 3:
            all_done.set()

    for index in range(3):
        seed_queued(
            env,
            f"job-{index}",
            f"source-{index}",
            queued_at=DEFAULT_NOW + timedelta(seconds=index),
        )
    fixture = make_runner(env, crawl=executor, scan_interval_seconds=3_600.0)
    start_runner_thread(fixture)
    try:
        env.wakeup.notify()

        assert all_done.wait(WAIT_TIMEOUT_SECONDS)
    finally:
        stop_runner_thread(fixture)

    assert done == ["job-0", "job-1", "job-2"]


def test_a_failing_scan_does_not_kill_the_runner_thread(caplog: pytest.LogCaptureFixture) -> None:
    env = make_env()
    executed = threading.Event()

    def executor(record: JobRecord, context: JobContext) -> None:
        succeed(record, context)
        executed.set()

    seed_queued(env)
    # 最初の走査は、リトライを尽くして失敗する(3 回)。次の走査で成功する。
    env.jobs_repository.behavior.inject(ops.LIST, StoreUnavailableError("timeout"), times=3)
    fixture = make_runner(env, crawl=executor, scan_interval_seconds=0.01)
    with caplog.at_level(logging.WARNING):
        start_runner_thread(fixture)
        try:
            assert executed.wait(WAIT_TIMEOUT_SECONDS)
        finally:
            stop_runner_thread(fixture)

    assert "job runner iteration failed" in caplog.text
    assert "StoreUnavailableError" in caplog.text


def test_a_stop_request_ends_an_idle_runner_promptly() -> None:
    fixture = make_runner(make_env(), scan_interval_seconds=3_600.0)
    fixture.runner.start()

    fixture.runner.request_stop()

    assert fixture.runner.join(WAIT_TIMEOUT_SECONDS)


def test_the_runner_cannot_be_started_twice() -> None:
    fixture = make_runner(make_env(), scan_interval_seconds=3_600.0)
    fixture.runner.start()
    try:
        with pytest.raises(RuntimeError):
            fixture.runner.start()
    finally:
        stop_runner_thread(fixture)


def test_the_executors_are_called_only_from_the_runner_thread() -> None:
    env = make_env()
    seed_queued(env)
    thread_names: list[str] = []
    executed = threading.Event()

    def executor(record: JobRecord, context: JobContext) -> None:
        thread_names.append(threading.current_thread().name)
        succeed(record, context)
        executed.set()

    fixture = make_runner(env, crawl=executor, scan_interval_seconds=0.01)
    fixture.runner.start()
    try:
        assert executed.wait(WAIT_TIMEOUT_SECONDS)
    finally:
        stop_runner_thread(fixture)

    assert thread_names == ["job-runner"]
