"""Scheduler の判定(architecture 4.3。テスト観点 #23)。

`run_once`(1 周。スレッドなし)で、cron 式の判定(前回の判定時刻より後で最初に合う時刻が現在以前か)・
受付の呼び出し・拒否の見送り・異常で落ちないことを、固定時計で確かめる。スレッドは
`test_scheduler_thread.py`。`make_scheduler` は `DEFAULT_NOW`(2026-11-13 00:00 UTC)で作るので、
その時刻が「前回の判定時刻」の初期値になる。
"""

import inspect
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.jobs import (
    Accepted,
    JobAdmission,
    JobStatus,
    LockAlreadyHeld,
    MaintenanceEnabled,
    SourceConfigNotFound,
    SourceDeleting,
)
from loreley_crawler.scheduler import SchedulerSettings
from loreley_crawler.scheduler import scheduler as scheduler_module
from loreley_crawler.sources import InvalidScheduleCron, SourceStatus
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW
from tests.jobs.support import JOB_ID, LOCK_ID, make_env
from tests.scheduler.support import (
    FIRST_FIRE_SECONDS,
    HOURLY_CRON,
    SOURCE_ID,
    after,
    make_scheduler,
    seed_crawl_job,
    seed_scheduled_source,
)

LATER_TOKEN = "1111abcd"


def queued_jobs(env: Any) -> list[str]:
    return [i for i in env.job_ids() if env.job_body(i)["status"] == "queued"]


# --- 起動してよいか(前回の判定時刻より後で最初に合う時刻が、現在以前か) ---

TOKYO = ZoneInfo("Asia/Tokyo")


def at(hour: int, minute: int = 0, second: int = 0, *, day: int = 13) -> datetime:
    return datetime(2026, 11, day, hour, minute, second, tzinfo=UTC)


def test_a_fire_time_passed_since_the_start_starts_a_crawl_exactly_at_that_time() -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, _ = make_scheduler(env)

    env.clock.set(at(0, 59, 59))
    scheduler.run_once()
    assert env.job_ids() == []  # 01:00 の 1 秒前

    env.clock.set(at(1, 0, 0))
    scheduler.run_once()
    assert len(env.job_ids()) == 1  # ちょうどの時刻で起動する


def test_the_start_time_itself_is_not_a_fire_time_of_the_run() -> None:
    env = make_env()
    seed_scheduled_source(env)
    env.clock.set(at(1, 0, 0))  # 起動の時刻が、cron の時刻ちょうど
    scheduler, _ = make_scheduler(env)

    scheduler.run_once()
    scheduler.run_once()
    assert env.job_ids() == []

    env.clock.set(at(1, 59, 59))
    scheduler.run_once()
    assert env.job_ids() == []

    env.clock.set(at(2, 0, 0))
    scheduler.run_once()
    assert len(env.job_ids()) == 1


def test_fire_times_that_passed_while_the_crawler_was_not_running_are_not_started() -> None:
    env = make_env()
    seed_scheduled_source(env, updated_at=DEFAULT_NOW)
    seed_crawl_job(env, 1, DEFAULT_NOW)  # 5 時間半前の最後のクロール
    env.clock.set(at(5, 30))  # 01:00〜05:00 の 5 回は、停止中に過ぎた(Scheduler は 05:30 に始まる)
    scheduler, admission = make_scheduler(env)

    scheduler.run_once()  # 起動直後の判定
    assert admission.scheduled_calls == []
    assert len(env.job_ids()) == 1  # 最初からあった記録だけ

    env.clock.set(at(6, 0, 0))
    scheduler.run_once()
    assert len(env.job_ids()) == 2  # 起動後に過ぎた 06:00 から起動する


def test_several_fire_times_between_two_passes_start_one_crawl() -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, admission = make_scheduler(env)

    env.clock.set(at(10, 30))  # 01:00〜10:00 の 10 回が、1 つの tick の間に過ぎた
    scheduler.run_once()
    scheduler.run_once()

    assert len(env.job_ids()) == 1
    assert len(admission.scheduled_calls) == 1


def test_after_a_pass_only_the_times_after_it_are_judged() -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, _ = make_scheduler(env, random_token=iter(["aaaa0001", "aaaa0002"]).__next__)
    env.clock.set(at(1, 0, 30))
    scheduler.run_once()
    [first] = env.job_ids()
    env.jobs_repository.delete_ids([LOCK_ID])  # 起動したジョブが終わり、ロックが解放された

    env.clock.set(at(1, 59, 59))
    scheduler.run_once()
    assert env.job_ids() == [first]  # 01:00 はもう判定済み

    env.clock.set(at(2, 0, 0))
    scheduler.run_once()
    assert len(env.job_ids()) == 2


def test_a_crawl_job_and_the_config_update_time_are_not_the_basis_of_the_judgment() -> None:
    env = make_env()
    # 設定の更新も手動クロールも、cron の時刻の直前・直後にある。
    seed_scheduled_source(env, updated_at=at(1, 30))
    manual_job_id = seed_crawl_job(env, 1, at(0, 59, 30), status=JobStatus.SUCCEEDED)
    scheduler, _ = make_scheduler(env)

    env.clock.set(at(1, 0, 0))
    scheduler.run_once()

    scheduled = [i for i in env.job_ids() if i != manual_job_id]
    assert [env.job_body(i)["trigger"] for i in scheduled] == ["schedule"]


def test_a_garbled_job_record_does_not_matter_because_job_records_are_not_read() -> None:
    env = make_env()
    seed_scheduled_source(env)
    job_id = seed_crawl_job(env, 1, DEFAULT_NOW)
    env.jobs_repository.seed(job_id, {**env.job_body(job_id), "queued_at": "garbled"})
    scheduler, admission = make_scheduler(env)

    env.clock.set(at(1, 0, 0))
    scheduler.run_once()

    assert len(admission.scheduled_calls) == 1


def test_each_source_is_judged_with_its_own_cron() -> None:
    env = make_env()
    seed_scheduled_source(env, "fast", cron="* * * * *")
    seed_scheduled_source(env, "slow", cron="0 12 * * *")
    scheduler, _ = make_scheduler(env)

    env.clock.set(after(DEFAULT_NOW, 60))
    scheduler.run_once()

    assert [env.job_body(i)["source_id"] for i in env.job_ids()] == ["fast"]


@pytest.mark.parametrize(
    ("zone", "last_before", "fire_at"),
    [
        # `0 9 * * *`: UTC なら 09:00 UTC、Asia/Tokyo(+09:00)なら 00:00 UTC(= 09:00 JST)。
        (UTC, at(8, 59, 59), at(9, 0, 0)),
        (TOKYO, at(23, 59, 59), at(0, 0, 0, day=14)),
    ],
    ids=["UTC", "Asia/Tokyo"],
)
def test_the_cron_is_read_in_the_configured_time_zone(
    zone: Any, last_before: datetime, fire_at: datetime
) -> None:
    env = make_env()
    seed_scheduled_source(env, cron="0 9 * * *")
    scheduler, _ = make_scheduler(env, timezone=zone)

    env.clock.set(last_before)
    scheduler.run_once()
    assert env.job_ids() == []  # その時刻の 1 秒前

    env.clock.set(fire_at)
    scheduler.run_once()
    assert len(env.job_ids()) == 1


def test_the_start_time_zone_decides_whether_a_time_in_the_past_is_a_fire_time() -> None:
    """Asia/Tokyo では、00:00 UTC の起動は 09:00 JST(ちょうどの時刻)で、それは起動しない。"""
    env = make_env()
    seed_scheduled_source(env, cron="0 9 * * *")
    scheduler, _ = make_scheduler(env, timezone=TOKYO)  # 起動は 2026-11-13 00:00 UTC

    scheduler.run_once()

    assert env.job_ids() == []


def test_a_clock_that_went_backwards_does_not_start_a_crawl_and_realigns_the_pass_time() -> None:
    env = make_env()
    seed_scheduled_source(env)
    env.clock.set(at(5, 30))
    scheduler, admission = make_scheduler(env)

    env.clock.set(at(3, 30))  # 2 時間戻る
    scheduler.run_once()
    assert env.job_ids() == []

    env.clock.set(at(3, 59, 59))
    scheduler.run_once()
    assert env.job_ids() == []  # 戻った先の時刻が、新しい前回の判定時刻

    env.clock.set(at(4, 0, 0))
    scheduler.run_once()
    assert len(admission.scheduled_calls) == 1  # 戻った後に、あらためて進んだ時刻は判定する


def test_a_clock_at_the_extreme_end_does_not_raise_and_starts_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    seed_scheduled_source(env, cron="0 0 1 1 *")
    env.clock.set(datetime(9999, 12, 31, tzinfo=UTC))
    scheduler, _ = make_scheduler(env)
    env.clock.set(datetime(9999, 12, 31, 23, 59, tzinfo=UTC))

    with caplog.at_level(logging.WARNING):
        scheduler.run_once()  # 次に合う時刻(10000 年)は日時の範囲を超える

    assert env.job_ids() == []
    assert "scheduler skipped a source because of an error: source_id=docs" in caplog.text


def test_a_source_with_no_next_fire_time_is_skipped_with_a_fixed_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def no_time(*args: object, **kwargs: object) -> datetime:
        raise InvalidScheduleCron("SENTINEL")

    env = make_env()
    seed_scheduled_source(env)
    scheduler, admission = make_scheduler(env)
    monkeypatch.setattr(scheduler_module, "next_fire_time", no_time)
    env.clock.set(at(1, 0, 0))

    with caplog.at_level(logging.WARNING):
        scheduler.run_once()

    assert admission.scheduled_calls == []
    assert "scheduler skipped a source with no next fire time: source_id=docs" in caplog.text
    assert "SENTINEL" not in caplog.text


def test_a_source_registered_between_two_passes_is_judged_from_the_last_pass() -> None:
    env = make_env()
    scheduler, _ = make_scheduler(env)
    env.clock.set(at(0, 30))
    scheduler.run_once()  # 対象のソースはまだない

    seed_scheduled_source(env, updated_at=at(0, 45))  # tick の合間に登録された
    env.clock.set(at(1, 0, 10))
    scheduler.run_once()

    assert len(env.job_ids()) == 1  # 前回の判定時刻(00:30)より後の 01:00 が対象


def test_the_cron_read_at_the_judgment_is_used_when_the_config_changed_between_passes() -> None:
    env = make_env()
    seed_scheduled_source(env, cron="0 3 * * *")
    scheduler, _ = make_scheduler(env)
    env.clock.set(at(0, 30))
    scheduler.run_once()

    seed_scheduled_source(env, cron=HOURLY_CRON)  # 毎時に更新された
    env.clock.set(at(1, 0, 10))
    scheduler.run_once()

    assert len(env.job_ids()) == 1


def test_a_source_changed_to_manual_only_between_passes_is_not_started() -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, admission = make_scheduler(env)
    env.clock.set(at(0, 30))
    scheduler.run_once()

    seed_scheduled_source(env, cron=None)
    env.clock.set(at(1, 0, 10))
    scheduler.run_once()

    assert admission.scheduled_calls == []


# --- 対象のソース ---


def test_a_source_without_a_schedule_is_never_started() -> None:
    env = make_env()
    seed_scheduled_source(env, cron=None)
    scheduler, admission = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, 10**7))

    scheduler.run_once()

    assert env.job_ids() == []
    assert admission.scheduled_calls == []


def test_a_deleting_source_is_never_started() -> None:
    env = make_env()
    seed_scheduled_source(env, status=SourceStatus.DELETING)
    scheduler, admission = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, 10**7))

    scheduler.run_once()

    assert env.job_ids() == []
    assert admission.scheduled_calls == []


# --- 受付の呼び出し ---


def test_a_scheduled_crawl_is_accepted_with_force_delete_and_rewrite_mode_always_false() -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, admission = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))

    scheduler.run_once()

    [(source_id, result)] = admission.scheduled_calls
    assert source_id == SOURCE_ID and isinstance(result, Accepted)
    [job_id] = env.job_ids()
    body = env.job_body(job_id)
    assert (body["job_type"], body["trigger"], body["status"]) == ("crawl", "schedule", "queued")
    assert (body["force_delete"], body["rewrite_mode"]) == (False, False)
    assert body["owner"] == env.settings.owner
    assert body["queued_at"] == "2026-11-13T01:00:00.000Z"
    lock = env.lock_body()
    assert lock is not None and lock["job_id"] == job_id


def test_the_scheduler_has_no_way_to_pass_force_delete_or_rewrite_mode() -> None:
    parameters = inspect.signature(JobAdmission.accept_scheduled_crawl).parameters
    assert list(parameters) == ["self", "source_id"]


def test_a_manual_crawl_entry_is_never_used() -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, admission = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))

    scheduler.run_once()

    assert admission.manual_calls == 0


def test_the_accepted_job_wakes_the_runner() -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, _ = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))

    scheduler.run_once()

    assert env.wakeup.wait(0) is True


# --- 一度起動したら、次の期限まで起動しない / 停止中の起動を取り返さない ---


def test_after_a_start_the_next_pass_does_not_start_again() -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, admission = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))

    scheduler.run_once()
    scheduler.run_once()

    assert len(env.job_ids()) == 1
    assert len(admission.scheduled_calls) == 1  # 受付を呼ぶのは期限を過ぎたときだけ


def test_missed_starts_while_stopped_are_not_made_up_and_one_start_follows() -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, _ = make_scheduler(env)

    env.clock.set(after(DEFAULT_NOW, 10 * FIRST_FIRE_SECONDS + 5))  # 10 回分を逃した
    scheduler.run_once()
    scheduler.run_once()

    assert len(env.job_ids()) == 1  # 再開後に 1 回だけ起動する


def test_a_pass_after_one_more_interval_starts_the_next_one() -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, _ = make_scheduler(env, random_token=iter(["aaaa0001", "aaaa0002"]).__next__)

    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
    scheduler.run_once()
    first = env.job_ids()
    # 起動したジョブが終わり、ロックが解放された。
    env.jobs_repository.delete_ids([LOCK_ID])
    env.clock.set(after(DEFAULT_NOW, 2 * FIRST_FIRE_SECONDS - 1))
    scheduler.run_once()
    assert env.job_ids() == first

    env.clock.set(after(DEFAULT_NOW, 2 * FIRST_FIRE_SECONDS))
    scheduler.run_once()
    assert len(env.job_ids()) == 2


# --- 拒否は見送るだけ ---


def test_a_held_lock_skips_the_round_without_writing_anything() -> None:
    env = make_env()
    seed_scheduled_source(env)
    env.seed_lock(JOB_ID)  # 実行中のジョブ(別のジョブの記録は期限の起点に影響しない)
    scheduler, admission = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
    records_before = env.jobs_repository.record_ids()
    lock_before = env.lock_body()

    scheduler.run_once()

    [(_, result)] = admission.scheduled_calls
    assert isinstance(result, LockAlreadyHeld)
    assert env.job_ids() == []
    assert env.jobs_repository.record_ids() == records_before == [LOCK_ID]
    assert env.lock_body() == lock_before  # 他のジョブのロックに触れない


def test_a_skipped_fire_time_is_not_made_up_when_the_lock_is_freed() -> None:
    env = make_env()
    seed_scheduled_source(env)
    env.seed_lock(JOB_ID)
    scheduler, admission = make_scheduler(env)

    env.clock.set(at(1, 0, 0))
    scheduler.run_once()  # 01:00 はロックで見送り
    [(_, result)] = admission.scheduled_calls
    assert isinstance(result, LockAlreadyHeld)

    env.jobs_repository.delete_ids([LOCK_ID])
    for tick in (at(1, 0, 30), at(1, 30), at(1, 59, 59)):
        env.clock.set(tick)
        scheduler.run_once()
    assert env.job_ids() == []  # 見送った 01:00 を取り返さず、待ち行列も作らない
    assert len(admission.scheduled_calls) == 1

    env.clock.set(at(2, 0, 0))
    scheduler.run_once()
    assert len(env.job_ids()) == 1  # 次の時刻(02:00)で起動する


def test_the_maintenance_flag_skips_the_round() -> None:
    env = make_env()
    seed_scheduled_source(env)
    env.seed_maintenance(True)
    scheduler, admission = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))

    scheduler.run_once()

    [(_, result)] = admission.scheduled_calls
    assert isinstance(result, MaintenanceEnabled)
    assert env.job_ids() == [] and env.lock_body() is None


def test_a_source_that_became_deleting_after_the_listing_is_skipped() -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, admission = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
    env.sources_repository.behavior.before(
        ops.FETCH, lambda: seed_scheduled_source(env, status=SourceStatus.DELETING)
    )

    scheduler.run_once()

    [(_, result)] = admission.scheduled_calls
    assert isinstance(result, SourceDeleting)
    assert env.job_ids() == [] and env.lock_body() is None


def test_a_source_whose_config_vanished_after_the_listing_is_skipped() -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, admission = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
    env.sources_repository.behavior.before(
        ops.FETCH, lambda: env.sources_repository.delete_ids([SOURCE_ID])
    )

    scheduler.run_once()

    [(_, result)] = admission.scheduled_calls
    assert isinstance(result, SourceConfigNotFound)
    assert env.job_ids() == [] and env.lock_body() is None


def test_a_routine_rejection_is_logged_at_debug_with_a_fixed_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """メンテナンス中・削除中・ロック中の見送りは、受付の判断の結果なので、INFO には出さない。"""
    env = make_env()
    seed_scheduled_source(env)
    env.seed_maintenance(True)
    scheduler, _ = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))

    with caplog.at_level(logging.INFO):
        scheduler.run_once()
    assert "scheduled crawl skipped" not in caplog.text

    env.clock.set(after(DEFAULT_NOW, 2 * FIRST_FIRE_SECONDS))  # 次の時刻
    with caplog.at_level(logging.DEBUG):
        scheduler.run_once()
    assert "scheduled crawl skipped: source_id=docs reason=maintenance_enabled" in caplog.text


# --- 異常で落ちない ---


def test_a_failure_to_list_the_sources_does_not_raise_and_the_next_pass_recovers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, _ = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
    env.sources_repository.behavior.inject(ops.LIST, StoreUnavailableError("timeout"), times=3)

    with caplog.at_level(logging.WARNING):
        scheduler.run_once()  # リトライを尽くして失敗

    assert env.job_ids() == []
    assert "scheduler could not list the sources: error=StoreUnavailableError" in caplog.text
    scheduler.run_once()
    assert len(env.job_ids()) == 1


def test_a_transient_failure_of_the_listing_is_retried_within_a_pass() -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, _ = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
    env.sources_repository.behavior.inject(ops.LIST, StoreUnavailableError("timeout"), times=2)

    scheduler.run_once()

    assert len(env.job_ids()) == 1


@pytest.mark.parametrize(
    "error",
    [StoreUnexpectedResponseError("source_list_truncated"), RuntimeError("unexpected")],
)
def test_an_unexpected_failure_of_the_listing_does_not_raise(error: Exception) -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, _ = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
    env.sources_repository.behavior.inject(ops.LIST, error, times=None)

    scheduler.run_once()

    assert env.job_ids() == []


def test_a_failure_for_one_source_does_not_stop_the_other_sources(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    seed_scheduled_source(env, "a-src")
    seed_scheduled_source(env, "b-src")
    scheduler, _ = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
    # 最初のソースの受付(設定の読み取り)が、リトライを尽くして失敗する。
    env.sources_repository.behavior.inject(
        ops.FETCH, StoreUnavailableError("timeout"), key="a-src", times=3
    )

    with caplog.at_level(logging.WARNING):
        scheduler.run_once()

    assert [env.job_body(i)["source_id"] for i in env.job_ids()] == ["b-src"]
    assert "scheduler skipped a source because of an error: source_id=a-src" in caplog.text
    assert "error=StoreUnavailableError" in caplog.text


def test_a_failure_is_logged_with_the_fixed_error_type_name_and_no_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, _ = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
    unexpected = StoreUnexpectedResponseError("malformed_job_record")
    env.sources_repository.behavior.inject(ops.FETCH, unexpected, times=None)

    with caplog.at_level(logging.WARNING):
        scheduler.run_once()

    assert (
        "scheduler skipped a source because of an error: source_id=docs "
        "error=StoreUnexpectedResponseError(malformed_job_record)"
    ) in caplog.text


def test_an_error_in_the_admission_does_not_stop_the_other_sources() -> None:
    env = make_env()
    seed_scheduled_source(env, "a-src")
    seed_scheduled_source(env, "b-src")
    scheduler, _ = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
    env.jobs_repository.behavior.inject(ops.CREATE, RuntimeError("boom"), key="lock-a-src")

    scheduler.run_once()

    assert [env.job_body(i)["source_id"] for i in env.job_ids()] == ["b-src"]


def test_a_malformed_source_is_skipped_and_the_others_are_still_started(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    seed_scheduled_source(env, "a-bad")
    body = env.sources_repository.body_of("a-bad")
    assert body is not None
    del body["ttl"]
    env.sources_repository.seed("a-bad", body)
    seed_scheduled_source(env, "b-good")
    scheduler, _ = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))

    with caplog.at_level(logging.WARNING):
        scheduler.run_once()

    assert [env.job_body(i)["source_id"] for i in env.job_ids()] == ["b-good"]
    assert "scheduler skipped a malformed source config: source_id=a-bad invalid_fields=ttl" in (
        caplog.text
    )


def test_logs_carry_no_config_values_or_exception_messages(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    seed_scheduled_source(
        env,
        connector_config={
            "root": "/data",
            "credentials_ref": "SENTINEL_CONFIG_REF",
            "pw": "SENTINEL_SECRET",
        },
    )
    scheduler, _ = make_scheduler(env)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
    env.jobs_repository.behavior.inject(
        ops.CREATE, RuntimeError("SENTINEL_SECRET /data/x"), times=None
    )

    with caplog.at_level(logging.DEBUG):
        scheduler.run_once()

    assert caplog.records
    assert "SENTINEL" not in caplog.text
    assert "error=RuntimeError" in caplog.text


def test_settings_reject_a_non_positive_check_interval() -> None:
    for value in (0, -1.0):
        with pytest.raises(ValueError):
            SchedulerSettings(check_interval_seconds=value)
    assert SchedulerSettings().check_interval_seconds == 30.0


def test_a_time_that_occurs_twice_when_daylight_saving_ends_starts_exactly_one_crawl() -> None:
    """America/New_York の 2026-11-01 は 01:30 が 2 回ある(EDT と EST)。`30 1 * * *` は、1 回目の
    01:30 EDT(05:30 UTC)で起動し、2 回目の時間帯(06:00〜07:00 UTC)の判定では同じ時刻を
    繰り返し起動しない(cronsim は 2 回目の時間帯の起点に、1 回目の時刻を返すことがある)。"""
    env = make_env()
    seed_scheduled_source(env, cron="30 1 * * *")
    env.clock.set(datetime(2026, 11, 1, 4, 59, 0, tzinfo=UTC))
    scheduler, admission = make_scheduler(env, timezone=ZoneInfo("America/New_York"))

    end = datetime(2026, 11, 1, 8, 0, 0, tzinfo=UTC)
    while env.clock.now() < end:
        env.clock.set(env.clock.now() + timedelta(seconds=30))
        scheduler.run_once()

    assert len(admission.scheduled_calls) == 1
