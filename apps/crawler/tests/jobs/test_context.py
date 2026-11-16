"""`JobContext`(module 4.4。architecture 4.7・5.3・5.7・7.9。テスト観点 #14・#18・#25・#28・#33)。

確認点(所有・取り消し・メンテナンス)、中断できる待ち、確認点つきのリトライ、版条件つきの更新と
読み直し・所有権の喪失の検知、`running` への遷移・設定の追記・最終状態を確かめる。
ハートビートは本物を `ManualWaiter` で動かし(スレッドは待ちに入ったまま)、時間は固定時計で進める。
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta

import pytest

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.common.retry import Retrier, RetryPolicy
from loreley_crawler.infrastructure.opensearch import NotFound
from loreley_crawler.jobs import (
    CancellationRequested,
    Check,
    FailureReason,
    JobContext,
    JobNotStartable,
    JobStatus,
    MaintenanceDetected,
    OwnershipLost,
)
from loreley_crawler.jobs.locks import Heartbeat, LeaseSet
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW
from tests.fakes.lost_response_repository import LostResponseRepository
from tests.jobs.locks.support import SETTINGS, ManualWaiter
from tests.jobs.support import JOB_ID, LOCK_ID, SOURCE_ID, JobsEnv, make_env

SNAPSHOT = {
    "crawl_started_at": "2026-11-13T00:00:00.000Z",
    "ttl": 2_592_000,
    "ratio_threshold": 0.3,
    "min_delete_count": 10,
    "force_delete": False,
    "rewrite_mode": False,
}
SOURCE_UPDATED_AT = DEFAULT_NOW - timedelta(days=1)


@dataclass
class ContextFixture:
    env: JobsEnv
    context: JobContext
    heartbeat: Heartbeat
    sleeps: list[float]


def make_retrier(sleeps: list[float], *, slice_seconds: float = 1.0) -> Retrier:
    """待たずに、待ち秒数を記録する(試行 3 回。待ちは 1 秒・2 秒)。"""
    return Retrier(
        RetryPolicy(3, 1.0, 2.0, 30.0, 0.0),
        sleep=sleeps.append,
        wait_slice_seconds=slice_seconds,
    )


def build(
    env: JobsEnv, *, status: JobStatus = JobStatus.QUEUED, retrier: Retrier | None = None
) -> tuple[JobContext, Heartbeat, list[float]]:
    record = env.seed_job(JOB_ID, status=status)
    env.seed_lock(JOB_ID)
    lock = env.lock_store.read(SOURCE_ID)
    assert lock is not None
    leased = env.lock_store.set_lease(
        lock, lease_seconds=SETTINGS.lease_seconds, require_active_lease=False
    )
    assert isinstance(leased, LeaseSet)
    heartbeat = Heartbeat(env.lock_store, env.clock, SETTINGS, waiter=ManualWaiter())
    heartbeat.start(leased.lock, leased.lease_expires_at)
    sleeps: list[float] = []
    context = JobContext(
        record=record,
        job_store=env.job_store,
        heartbeat=heartbeat,
        cancel_requests=env.cancel_requests,
        read_maintenance_flag=env.read_maintenance_flag,
        clock=env.clock,
        retrier=retrier or make_retrier(sleeps),
    )
    return context, heartbeat, sleeps


@pytest.fixture
def fixture() -> Iterator[ContextFixture]:
    env = make_env()
    context, heartbeat, sleeps = build(env)
    yield ContextFixture(env, context, heartbeat, sleeps)
    heartbeat.stop()


@pytest.fixture
def running(fixture: ContextFixture) -> ContextFixture:
    fixture.context.start_running()
    return fixture


# --- 確認点 ---


def test_every_check_passes_while_nothing_is_wrong(fixture: ContextFixture) -> None:
    fixture.context.check()
    fixture.context.check(Check.OWNERSHIP)


def test_a_recorded_loss_is_reported_with_its_reason(fixture: ContextFixture) -> None:
    fixture.heartbeat.record_loss("lock_missing")

    with pytest.raises(OwnershipLost) as raised:
        fixture.context.check()

    assert raised.value.reason == "lock_missing"


def test_an_expired_lease_is_reported_without_any_store_access(fixture: ContextFixture) -> None:
    fixture.env.clock.advance(seconds=SETTINGS.lease_seconds)
    fixture.env.jobs_repository.behavior.inject(ops.FETCH, AssertionError("no I/O"), times=None)

    with pytest.raises(OwnershipLost) as raised:
        fixture.context.check(Check.OWNERSHIP)

    assert raised.value.reason == "lease_expired"


def test_a_cancel_request_is_reported(fixture: ContextFixture) -> None:  # テスト観点 #26
    fixture.env.cancel_requests.request(JOB_ID)

    with pytest.raises(CancellationRequested):
        fixture.context.check()

    fixture.context.check(Check.OWNERSHIP | Check.MAINTENANCE)  # 選ばなければ見ない


def test_another_jobs_cancel_request_is_not_ours(fixture: ContextFixture) -> None:
    fixture.env.cancel_requests.request("job-another")

    fixture.context.check()


@pytest.mark.parametrize("enabled", [True, "false", None, 0])
def test_a_raised_or_malformed_maintenance_flag_is_reported(
    fixture: ContextFixture, enabled: object
) -> None:  # テスト観点 #18
    fixture.env.seed_maintenance(enabled)

    with pytest.raises(MaintenanceDetected):
        fixture.context.check()


def test_the_flag_explicitly_false_is_not_maintenance(fixture: ContextFixture) -> None:
    fixture.env.seed_maintenance(False)

    fixture.context.check()


def test_the_maintenance_flag_is_read_only_when_it_is_selected(fixture: ContextFixture) -> None:
    fixture.env.seed_maintenance(True)

    fixture.context.check(Check.OWNERSHIP | Check.CANCELLATION)

    calls = fixture.env.jobs_repository.behavior.calls_of(ops.FETCH)
    assert [call for call in calls if call.key == "maintenance"] == []


def test_checks_are_made_in_the_order_ownership_cancellation_maintenance(
    fixture: ContextFixture,
) -> None:
    fixture.env.seed_maintenance(True)
    fixture.env.cancel_requests.request(JOB_ID)

    with pytest.raises(CancellationRequested):
        fixture.context.check()

    fixture.heartbeat.record_loss("lock_missing")
    with pytest.raises(OwnershipLost):
        fixture.context.check()


def test_a_transient_failure_reading_the_flag_is_retried(fixture: ContextFixture) -> None:
    fixture.env.jobs_repository.behavior.inject(
        ops.FETCH, StoreUnavailableError("timeout"), key="maintenance", times=2
    )

    fixture.context.check()


def test_a_persistent_failure_reading_the_flag_is_raised_not_ignored(
    fixture: ContextFixture,
) -> None:
    fixture.env.jobs_repository.behavior.inject(
        ops.FETCH, StoreUnavailableError("timeout"), key="maintenance", times=None
    )

    with pytest.raises(StoreUnavailableError):
        fixture.context.check()


def test_a_lock_not_owned_reply_is_recorded_as_a_loss(fixture: ContextFixture) -> None:
    fixture.context.record_lock_not_owned()

    assert fixture.heartbeat.lost_reason == "lock_not_owned"
    with pytest.raises(OwnershipLost) as raised:
        fixture.context.check()
    assert raised.value.reason == "lock_not_owned"


# --- 中断できる待ち ---


def test_a_wait_sleeps_in_slices_and_checks_before_each(fixture: ContextFixture) -> None:
    fixture.context.wait(2.5)

    assert fixture.sleeps == [1.0, 1.0, 0.5]


def test_a_cancel_request_interrupts_a_wait_at_the_next_slice() -> None:
    env = make_env()
    sleeps: list[float] = []

    def sleep_then_cancel(seconds: float) -> None:
        sleeps.append(seconds)
        env.cancel_requests.request(JOB_ID)

    retrier = Retrier(
        RetryPolicy(3, 1.0, 2.0, 30.0, 0.0), sleep=sleep_then_cancel, wait_slice_seconds=1.0
    )
    context, heartbeat, _ = build(env, retrier=retrier)
    try:
        with pytest.raises(CancellationRequested):
            context.wait(10.0)

        assert sleeps == [1.0]  # 1 回目の待ちの後の確認点で止まる(残りは待たない)
    finally:
        heartbeat.stop()


def test_a_lost_ownership_interrupts_a_wait(fixture: ContextFixture) -> None:
    fixture.heartbeat.record_loss("lock_missing")

    with pytest.raises(OwnershipLost):
        fixture.context.wait(5.0)

    assert fixture.sleeps == []


def test_a_wait_does_not_read_the_maintenance_flag_by_default(fixture: ContextFixture) -> None:
    fixture.env.seed_maintenance(True)

    fixture.context.wait(2.0)  # 例外にならない


def test_a_wait_can_select_the_maintenance_flag(fixture: ContextFixture) -> None:
    fixture.env.seed_maintenance(True)

    with pytest.raises(MaintenanceDetected):
        fixture.context.wait(2.0, Check.ALL)


# --- 確認点つきのリトライ ---


def test_the_retrier_checks_before_every_attempt(fixture: ContextFixture) -> None:
    attempts = 0

    def always_fails() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            fixture.env.cancel_requests.request(JOB_ID)  # 1 回目の試行の最中に取り消される
        raise StoreUnavailableError("timeout")

    with pytest.raises(CancellationRequested):
        fixture.context.retrier().run(
            always_fails, is_retryable_error=lambda e: isinstance(e, StoreUnavailableError)
        )

    assert attempts == 1  # 2 回目の試行(と待ち)の前の確認点で止まる
    assert fixture.sleeps == []


def test_the_retrier_stops_retrying_after_the_ownership_is_lost(fixture: ContextFixture) -> None:
    attempts = 0

    def fails_and_loses_ownership() -> None:
        nonlocal attempts
        attempts += 1
        fixture.heartbeat.record_loss("lock_not_owned")
        raise StoreUnavailableError("timeout")

    with pytest.raises(OwnershipLost):
        fixture.context.retrier(Check.OWNERSHIP).run(
            fails_and_loses_ownership,
            is_retryable_error=lambda e: isinstance(e, StoreUnavailableError),
        )

    assert attempts == 1


def test_the_retrier_runs_the_full_attempts_when_checks_pass(fixture: ContextFixture) -> None:
    attempts = 0

    def always_fails() -> None:
        nonlocal attempts
        attempts += 1
        raise StoreUnavailableError("timeout")

    with pytest.raises(StoreUnavailableError):
        fixture.context.retrier().run(
            always_fails, is_retryable_error=lambda e: isinstance(e, StoreUnavailableError)
        )

    assert attempts == 3
    assert sum(fixture.sleeps) == 3.0  # バックオフ 1 秒・2 秒(1 秒ずつに区切って待つ)


def test_the_retrier_checks_the_maintenance_flag_for_every_attempt(fixture: ContextFixture) -> None:
    fixture.env.seed_maintenance(False)
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            fixture.env.seed_maintenance(True)  # 1 回目の試行の最中に、フラグが立つ
        raise StoreUnavailableError("timeout")

    with pytest.raises(MaintenanceDetected):
        fixture.context.retrier().run(
            operation, is_retryable_error=lambda e: isinstance(e, StoreUnavailableError)
        )

    assert attempts == 1


# --- queued -> running(テスト観点 #25) ---


def test_start_running_records_started_at_and_returns_it(fixture: ContextFixture) -> None:
    started_at = fixture.context.start_running()

    assert started_at == "2026-11-13T00:00:00.000Z"
    body = fixture.env.job_body(JOB_ID)
    assert (body["status"], body["started_at"]) == ("running", started_at)
    assert fixture.context.record.status is JobStatus.RUNNING
    assert fixture.context.is_terminal is False


def test_start_running_loses_to_a_cancel_that_won_first(fixture: ContextFixture) -> None:
    fixture.env.jobs_repository.seed(
        JOB_ID, {**fixture.env.job_body(JOB_ID), "status": "cancelled", "finished_at": "x"}
    )

    with pytest.raises(JobNotStartable) as raised:
        fixture.context.start_running()

    assert raised.value.status is JobStatus.CANCELLED
    assert fixture.context.is_terminal is True
    assert fixture.heartbeat.lost_reason is None  # ロックは Job Runner が解放する
    assert fixture.env.job_body(JOB_ID)["status"] == "cancelled"  # 取り消しを上書きしない


def test_start_running_loses_when_the_record_vanished(fixture: ContextFixture) -> None:
    stored = fixture.env.jobs_repository.fetch(JOB_ID)
    assert stored is not None
    fixture.env.jobs_repository.delete_if_unchanged(
        JOB_ID, seq_no=stored.seq_no, primary_term=stored.primary_term
    )

    with pytest.raises(JobNotStartable) as raised:
        fixture.context.start_running()

    assert raised.value.status is None
    assert fixture.context.is_terminal is False


def test_start_running_retries_on_the_current_version_when_still_queued(
    fixture: ContextFixture,
) -> None:
    fixture.env.jobs_repository.seed(JOB_ID, {**fixture.env.job_body(JOB_ID), "note": "x"})

    fixture.context.start_running()

    body = fixture.env.job_body(JOB_ID)
    assert (body["status"], body["note"]) == ("running", "x")


def test_a_lost_response_of_the_start_is_a_success() -> None:
    repository = LostResponseRepository()
    env = make_env(repository)
    context, heartbeat, _ = build(env)
    try:
        repository.lose_response_of(ops.REPLACE)

        context.start_running()

        assert env.job_body(JOB_ID)["status"] == "running"
    finally:
        heartbeat.stop()


# --- 設定スナップショットの追記 ---


def test_settings_are_added_in_a_separate_conditional_update(running: ContextFixture) -> None:
    running.context.record_settings(SNAPSHOT, SOURCE_UPDATED_AT)

    body = running.env.job_body(JOB_ID)
    assert body["settings_snapshot"] == SNAPSHOT
    assert body["settings_source_updated_at"] == "2026-11-12T00:00:00.000Z"
    assert "settings_source_updated_at" not in body["settings_snapshot"]  # snapshot の外
    assert "connector_config" not in body
    replaces = running.env.jobs_repository.behavior.calls_of(ops.REPLACE)
    assert len([call for call in replaces if call.key == JOB_ID]) == 2  # `running` への遷移と追記


@pytest.mark.parametrize(
    "snapshot",
    [
        {**SNAPSHOT, "connector_config": {"root": "/data"}},  # 7 番目の項目
        {**SNAPSHOT, "settings_source_updated_at": "x"},
        {key: value for key, value in SNAPSHOT.items() if key != "ttl"},  # 欠落
        {},
    ],
)
def test_the_snapshot_must_have_exactly_the_six_fields(
    running: ContextFixture, snapshot: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        running.context.record_settings(snapshot, SOURCE_UPDATED_AT)

    assert "settings_snapshot" not in running.env.job_body(JOB_ID)


def test_the_snapshot_is_written_only_once(running: ContextFixture) -> None:
    running.context.record_settings(SNAPSHOT, SOURCE_UPDATED_AT)

    with pytest.raises(RuntimeError):
        running.context.record_settings(SNAPSHOT, SOURCE_UPDATED_AT)


# --- 版条件つきの更新と所有権の喪失の検知(テスト観点 #28) ---


def test_updates_chain_on_the_version_of_the_last_write(running: ContextFixture) -> None:
    running.context.update({"registration": {"partial": True}})
    running.context.update({"finish_notice": {"outcome": "enumeration_completed"}})

    body = running.env.job_body(JOB_ID)
    assert body["registration"] == {"partial": True}
    assert body["finish_notice"] == {"outcome": "enumeration_completed"}
    assert body["status"] == "running"


@pytest.mark.parametrize("field", ["status", "connector_config"])
def test_protected_fields_cannot_be_written_by_update(running: ContextFixture, field: str) -> None:
    with pytest.raises(ValueError):
        running.context.update({field: "x"})

    body = running.env.job_body(JOB_ID)
    assert body["status"] == "running"
    assert "connector_config" not in body


def test_an_update_after_the_admin_released_the_lock_is_a_lost_ownership(
    running: ContextFixture,
) -> None:
    """管理者のロック解放が `failed`(`lock_released`)にした後の Job Runner の更新。"""
    running.env.jobs_repository.seed(
        JOB_ID,
        {
            **running.env.job_body(JOB_ID),
            "status": "failed",
            "failure_reason": "lock_released",
            "finished_at": "2026-11-13T00:00:00.000Z",
        },
    )

    with pytest.raises(OwnershipLost) as raised:
        running.context.update({"registration": {"partial": True}})

    assert raised.value.reason == "job_record_superseded"
    assert running.heartbeat.lost_reason == "job_record_superseded"
    assert running.context.is_terminal is True
    body = running.env.job_body(JOB_ID)
    assert (body["status"], body["failure_reason"]) == ("failed", "lock_released")
    assert "registration" not in body  # 解放側の結果を上書きしない


def test_an_update_after_the_record_vanished_is_a_lost_ownership(running: ContextFixture) -> None:
    stored = running.env.jobs_repository.fetch(JOB_ID)
    assert stored is not None
    running.env.jobs_repository.delete_if_unchanged(
        JOB_ID, seq_no=stored.seq_no, primary_term=stored.primary_term
    )

    with pytest.raises(OwnershipLost):
        running.context.update({"registration": {}})

    assert running.context.is_terminal is False


def test_an_update_rereads_and_continues_when_the_job_is_still_running(
    running: ContextFixture,
) -> None:
    running.env.jobs_repository.seed(
        JOB_ID, {**running.env.job_body(JOB_ID), "diagnostic": "added by another writer"}
    )

    running.context.update({"registration": {"partial": True}})

    body = running.env.job_body(JOB_ID)
    assert body["registration"] == {"partial": True}
    assert body["diagnostic"] == "added by another writer"
    assert running.heartbeat.lost_reason is None


def test_a_lost_update_response_is_a_success() -> None:
    repository = LostResponseRepository()
    env = make_env(repository)
    context, heartbeat, _ = build(env, status=JobStatus.RUNNING)
    try:
        repository.lose_response_of(ops.REPLACE)

        context.update({"registration": {"partial": True}})

        assert env.job_body(JOB_ID)["registration"] == {"partial": True}
        assert heartbeat.lost_reason is None
    finally:
        heartbeat.stop()


def test_a_store_write_that_keeps_failing_raises_after_the_retries(
    running: ContextFixture,
) -> None:  # テスト観点 #33
    behavior = running.env.jobs_repository.behavior
    behavior.inject(ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=None)

    with pytest.raises(StoreUnavailableError):
        running.context.update({"registration": {}})

    assert len(behavior.calls_of(ops.REPLACE)) >= 3  # 試行 3 回を尽くした
    assert "registration" not in running.env.job_body(JOB_ID)


def test_a_transient_store_failure_in_an_update_is_retried(running: ContextFixture) -> None:
    running.env.jobs_repository.behavior.inject(
        ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=2
    )

    running.context.update({"registration": {"partial": True}})

    assert running.env.job_body(JOB_ID)["registration"] == {"partial": True}


def test_updates_are_retried_even_after_a_cancel_request(running: ContextFixture) -> None:
    """記録の書き込みは確認点を通さない(取り消し・喪失の後にも、最終状態を残すため)。"""
    running.env.cancel_requests.request(JOB_ID)
    running.heartbeat.record_loss("lock_not_owned")
    running.env.jobs_repository.behavior.inject(
        ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=1
    )

    running.context.update({"registration": {"partial": True}})

    assert running.env.job_body(JOB_ID)["registration"] == {"partial": True}


# --- 最終状態の記録 ---


def test_finish_records_the_final_state_and_clears_the_cancel_request(
    running: ContextFixture,
) -> None:
    running.env.cancel_requests.request(JOB_ID)

    recorded = running.context.finish(
        JobStatus.CANCELLED, changes={"registration": {"partial": True}}
    )

    assert recorded is True
    body = running.env.job_body(JOB_ID)
    assert body["status"] == "cancelled"
    assert body["finished_at"] == "2026-11-13T00:00:00.000Z"
    assert body["registration"] == {"partial": True}
    assert running.context.is_terminal is True
    assert not running.env.cancel_requests.is_requested(JOB_ID)


@pytest.mark.parametrize(
    "status", [JobStatus.SUCCEEDED, JobStatus.PARTIALLY_SUCCEEDED, JobStatus.CANCELLED]
)
def test_finish_records_every_non_failed_terminal_status(
    running: ContextFixture, status: JobStatus
) -> None:
    assert running.context.finish(status) is True

    body = running.env.job_body(JOB_ID)
    assert body["status"] == status.value
    assert "failure_reason" not in body


def test_a_failed_job_records_its_reason_and_a_cleaned_detail(running: ContextFixture) -> None:
    running.context.finish(
        JobStatus.FAILED,
        failure_reason=FailureReason.CONFIG_INVALID,
        failure_detail="line1\nline2\x00 lone\ud800 " + "x" * 600,
    )

    body = running.env.job_body(JOB_ID)
    assert body["failure_reason"] == "config_invalid"
    detail = body["failure_detail"]
    assert detail.startswith("line1\\nline2\\x00 lone� ")
    assert len(detail) <= 512


@pytest.mark.parametrize(
    "arguments",
    [
        {"status": JobStatus.FAILED},  # 理由なし
        {"status": JobStatus.SUCCEEDED, "failure_reason": FailureReason.INTERNAL_ERROR},
        {"status": JobStatus.RUNNING},
        {"status": JobStatus.QUEUED},
        {"status": JobStatus.CANCELLED, "changes": {"status": "x"}},
        {"status": JobStatus.CANCELLED, "changes": {"connector_config": {}}},
    ],
)
def test_finish_rejects_inconsistent_arguments(
    running: ContextFixture, arguments: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        running.context.finish(**arguments)  # type: ignore[arg-type]

    assert running.env.job_body(JOB_ID)["status"] == "running"
    assert running.context.is_terminal is False


def test_finish_does_not_overwrite_a_state_the_admin_changed(running: ContextFixture) -> None:
    running.env.jobs_repository.seed(
        JOB_ID,
        {
            **running.env.job_body(JOB_ID),
            "status": "failed",
            "failure_reason": "lock_released",
        },
    )

    recorded = running.context.finish(JobStatus.SUCCEEDED)

    assert recorded is False
    body = running.env.job_body(JOB_ID)
    assert (body["status"], body["failure_reason"]) == ("failed", "lock_released")
    assert running.heartbeat.lost_reason == "job_record_superseded"  # ロックを削除させない
    assert running.context.is_terminal is True


@pytest.mark.parametrize(
    "first",
    [
        {"status": JobStatus.SUCCEEDED},
        {"status": JobStatus.PARTIALLY_SUCCEEDED},
        {"status": JobStatus.CANCELLED},
        {"status": JobStatus.FAILED, "failure_reason": FailureReason.CONFIG_INVALID},
    ],
)
def test_finish_records_the_final_state_only_once(
    running: ContextFixture, first: dict[str, object]
) -> None:
    """終端の後に `finish` を呼んでも、何も書かず False を返す(最初の最終状態を変えない)。"""
    assert running.context.finish(**first) is True  # type: ignore[arg-type]
    after_first = running.env.job_body(JOB_ID)
    replaces_before = len(running.env.jobs_repository.behavior.calls_of(ops.REPLACE))

    again = running.context.finish(
        JobStatus.FAILED, failure_reason=FailureReason.INTERNAL_ERROR, failure_detail="late"
    )

    assert again is False
    assert running.env.job_body(JOB_ID) == after_first
    assert len(running.env.jobs_repository.behavior.calls_of(ops.REPLACE)) == replaces_before
    assert running.heartbeat.lost_reason is None  # 喪失ではない(自分が記録済み)
    assert running.context.is_terminal is True


def test_finish_can_end_a_job_that_never_started(fixture: ContextFixture) -> None:
    """最後の手段: `running` にする前に例外が出たジョブも、`failed` を記録できる。"""
    recorded = fixture.context.finish(JobStatus.FAILED, failure_reason=FailureReason.INTERNAL_ERROR)

    assert recorded is True
    assert fixture.env.job_body(JOB_ID)["status"] == "failed"


def test_finish_records_a_cancel_even_when_the_ownership_was_lost(running: ContextFixture) -> None:
    running.heartbeat.record_loss("lock_not_owned")
    running.env.cancel_requests.request(JOB_ID)

    assert running.context.finish(JobStatus.CANCELLED) is True


def test_failed_store_unavailable_can_be_recorded_after_the_outage_ends(
    running: ContextFixture,
) -> None:  # テスト観点 #33(jobs 側)
    behavior = running.env.jobs_repository.behavior
    behavior.inject(ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=3)
    with pytest.raises(StoreUnavailableError):
        running.context.update({"registration": {}})

    recorded = running.context.finish(
        JobStatus.FAILED, failure_reason=FailureReason.STORE_UNAVAILABLE
    )

    assert recorded is True
    assert running.env.job_body(JOB_ID)["failure_reason"] == "store_unavailable"


def test_record_writes_do_not_use_the_checkpoints_of_the_retrier_given_to_the_context() -> None:
    """確認点つきの `Retrier` を渡されても、記録の書き込みは確認点を通さない(R8 の対象外)。

    取り消し・喪失の後にも、最終状態を残すため。確認点を通すと、ここで例外になる。
    """

    def forbidden_checkpoint() -> None:
        raise AssertionError("record writes must not pass the checkpoints")

    env = make_env()
    retrier = Retrier(
        RetryPolicy(3, 1.0, 2.0, 30.0, 0.0),
        checkpoint=forbidden_checkpoint,
        sleep=lambda _seconds: None,
    )
    context, heartbeat, _ = build(env, status=JobStatus.RUNNING, retrier=retrier)
    try:
        env.cancel_requests.request(JOB_ID)
        heartbeat.record_loss("lock_not_owned")
        behavior = env.jobs_repository.behavior
        behavior.inject(ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=1)
        context.update({"registration": {"partial": True}})  # 失敗 1 回 + リトライ
        behavior.inject(ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=1)

        assert context.finish(JobStatus.CANCELLED) is True

        assert env.job_body(JOB_ID)["status"] == "cancelled"
    finally:
        heartbeat.stop()


def test_a_not_found_reply_to_a_conditional_write_is_treated_as_a_conflict(
    running: ContextFixture,
) -> None:
    """`Written`・`Deleted` 以外は、競合として読み直す(実機では記録がなくても 409 だが、
    `NotFound` が返っても安全に動く)。"""
    running.env.jobs_repository.behavior.inject(ops.REPLACE, NotFound(), key=JOB_ID, times=1)

    running.context.update({"registration": {"partial": True}})

    assert running.env.job_body(JOB_ID)["registration"] == {"partial": True}
    assert running.heartbeat.lost_reason is None


def test_the_lock_document_is_not_touched_by_the_context(running: ContextFixture) -> None:
    before = running.env.jobs_repository.body_of(LOCK_ID)

    running.context.update({"registration": {}})
    running.context.finish(JobStatus.SUCCEEDED)

    assert running.env.jobs_repository.body_of(LOCK_ID) == before
