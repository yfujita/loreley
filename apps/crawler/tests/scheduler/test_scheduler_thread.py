"""Scheduler のスレッド: 周期の待ち・停止要求(module 2.2。スリープに頼らない)。

待ちは `ManualWaiter` で 1 周ずつ進める。待ち・合流には必ず上限を付ける。
"""

import threading

import pytest

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.scheduler import Scheduler
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW
from tests.jobs.locks.support import ManualWaiter
from tests.jobs.support import LOCK_ID, WAIT_TIMEOUT_SECONDS, make_env
from tests.scheduler.support import (
    CHECK_INTERVAL_SECONDS,
    FIRST_FIRE_SECONDS,
    after,
    make_scheduler,
    seed_scheduled_source,
)


def stop(scheduler: Scheduler) -> None:
    scheduler.request_stop()
    assert scheduler.join(WAIT_TIMEOUT_SECONDS)


def test_the_first_pass_runs_at_once_and_each_wait_is_the_check_interval() -> None:
    env = make_env()
    seed_scheduled_source(env)
    waiter = ManualWaiter()
    scheduler, _ = make_scheduler(env, waiter=waiter)

    scheduler.start()
    try:
        waiter.wait_until_waiting(1)  # 1 周目が終わって、待ちに入った

        assert env.job_ids() == []  # 起動の時刻より前に過ぎた時刻はない
        assert waiter.requested_waits == [CHECK_INTERVAL_SECONDS]
    finally:
        stop(scheduler)


def test_start_ignores_the_times_that_passed_between_the_assembly_and_the_start() -> None:
    """組み立ての後、起動時の回復などの間に過ぎた時刻は、起動しない。"""
    env = make_env()
    seed_scheduled_source(env)
    waiter = ManualWaiter()
    scheduler, admission = make_scheduler(env, waiter=waiter)  # 00:00 に組み立てた
    env.clock.set(after(DEFAULT_NOW, 3 * FIRST_FIRE_SECONDS + 1_800))  # 回復の間に 3 回過ぎた

    scheduler.start()
    try:
        waiter.wait_until_waiting(1)

        assert admission.scheduled_calls == []
        assert env.job_ids() == []
    finally:
        stop(scheduler)


def test_each_released_tick_runs_one_more_pass_that_judges_with_the_current_time() -> None:
    env = make_env()
    seed_scheduled_source(env)
    waiter = ManualWaiter()
    scheduler, admission = make_scheduler(env, waiter=waiter)

    scheduler.start()
    try:
        waiter.wait_until_waiting(1)
        assert env.job_ids() == []  # 期限の前

        env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
        waiter.release_tick()
        waiter.wait_until_waiting(2)

        assert len(env.job_ids()) == 1
        assert waiter.requested_waits == [CHECK_INTERVAL_SECONDS] * 2
        assert admission.thread_names == ["scheduler"]  # 受付は Scheduler のスレッドで呼ばれる
    finally:
        stop(scheduler)


def test_a_stop_request_ends_the_thread_promptly_even_while_waiting() -> None:
    env = make_env()
    seed_scheduled_source(env)
    waiter = ManualWaiter()
    scheduler, _ = make_scheduler(env, waiter=waiter)
    scheduler.start()
    waiter.wait_until_waiting(1)

    scheduler.request_stop()

    assert scheduler.join(WAIT_TIMEOUT_SECONDS)


def test_a_tick_released_after_the_stop_request_runs_no_pass() -> None:
    """停止要求の後に待ちが解けても(期限も過ぎていても)、次の周回に入らずにスレッドが終わる。"""
    env = make_env()
    seed_scheduled_source(env)
    waiter = ManualWaiter()
    scheduler, _ = make_scheduler(env, waiter=waiter)
    scheduler.start()
    waiter.wait_until_waiting(1)

    scheduler.request_stop()  # 待ちの中のスレッドへ、まず停止を伝える
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
    waiter.release_tick()
    assert scheduler.join(WAIT_TIMEOUT_SECONDS)

    assert env.job_ids() == []
    assert len(waiter.requested_waits) == 1  # 停止後に、次の待ち・周回に入らない


def test_a_stop_request_before_the_start_runs_no_pass() -> None:
    env = make_env()
    seed_scheduled_source(env)
    scheduler, admission = make_scheduler(env, waiter=ManualWaiter())
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))

    scheduler.request_stop()
    scheduler.run_until_stopped()  # 呼び出したスレッドで、すぐ戻る

    assert admission.scheduled_calls == []


def test_a_stop_request_during_a_pass_stops_before_the_next_source() -> None:
    env = make_env()
    seed_scheduled_source(env, "a-src")
    seed_scheduled_source(env, "b-src")
    # 2 件の受付が同じジョブ ID にならないよう、乱数を替える。
    tokens = iter(["aaaa0001", "aaaa0002"])
    scheduler, _ = make_scheduler(env, waiter=ManualWaiter(), random_token=tokens.__next__)
    env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
    # 最初のソースの受付(設定の読み取り)の直前に、停止を要求する。
    env.sources_repository.behavior.before(ops.FETCH, scheduler.request_stop)

    scheduler.run_once()

    # 最初のソースの判定中に停止が要求された。最初のソースは済み、次のソースは始めない。
    assert [env.job_body(i)["source_id"] for i in env.job_ids()] == ["a-src"]


def test_a_failing_pass_does_not_kill_the_thread_and_the_next_tick_recovers() -> None:
    env = make_env()
    seed_scheduled_source(env)
    env.sources_repository.behavior.inject(ops.LIST, StoreUnavailableError("timeout"), times=3)
    waiter = ManualWaiter()
    scheduler, _ = make_scheduler(env, waiter=waiter)

    scheduler.start()
    try:
        waiter.wait_until_waiting(1)  # 1 周目は、一覧の取得に失敗した
        env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
        assert env.job_ids() == []

        waiter.release_tick()
        waiter.wait_until_waiting(2)

        assert len(env.job_ids()) == 1
    finally:
        stop(scheduler)


def test_the_thread_is_a_daemon_and_cannot_be_started_twice() -> None:
    env = make_env()
    waiter = ManualWaiter()
    scheduler, _ = make_scheduler(env, waiter=waiter)
    scheduler.start()
    try:
        [thread] = [t for t in threading.enumerate() if t.name == "scheduler"]
        assert thread.daemon is True
        with pytest.raises(RuntimeError):
            scheduler.start()
    finally:
        stop(scheduler)


def test_join_without_start_returns_true() -> None:
    scheduler, _ = make_scheduler(make_env(), waiter=ManualWaiter())

    assert scheduler.join(0.0) is True


def test_the_default_waiter_stops_on_request() -> None:
    """結果は、停止要求が 1 周目の前・中・後のどこで届いても変わらない(スレッドが終わること)。"""
    env = make_env()
    scheduler, _ = make_scheduler(env)  # 既定の `EventTickWaiter`(30 秒の待ち)
    scheduler.start()

    scheduler.request_stop()

    assert scheduler.join(WAIT_TIMEOUT_SECONDS)


def test_a_started_lock_is_visible_to_the_runner_after_the_pass() -> None:
    env = make_env()
    seed_scheduled_source(env)
    waiter = ManualWaiter()
    scheduler, _ = make_scheduler(env, waiter=waiter)
    scheduler.start()
    try:
        waiter.wait_until_waiting(1)
        env.clock.set(after(DEFAULT_NOW, FIRST_FIRE_SECONDS))
        waiter.release_tick()
        waiter.wait_until_waiting(2)

        assert LOCK_ID in env.jobs_repository.record_ids()
    finally:
        stop(scheduler)


def test_a_waiter_that_reports_a_stop_ends_the_loop() -> None:
    """停止が待ち(`TickWaiter`)の側から伝わった場合も、ループを終える。"""
    env = make_env()
    waiter = ManualWaiter()
    scheduler, _ = make_scheduler(env, waiter=waiter)
    scheduler.start()
    waiter.wait_until_waiting(1)

    waiter.stop()

    assert scheduler.join(WAIT_TIMEOUT_SECONDS)
