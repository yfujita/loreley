"""ハートビート(architecture 5.3・5.5・5.7。テスト観点 #13・#32 の単体部分)。

更新の規則は `tick()` を直接呼んで、スレッドなしで確かめる。スレッドのテストは、待ちを
`ManualWaiter` で 1 回ずつ進め、`Event`・固定時計・ゲートで書く(スリープに頼らない)。
`join` などの待ちには、必ず上限を付ける。
"""

import logging
import threading
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import pytest

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.infrastructure.opensearch import ReplaceOutcome
from loreley_crawler.jobs.locks import Heartbeat, HeartbeatSettings, LockStore
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.in_memory_repository import InMemoryRepository
from tests.jobs.locks.support import (
    JOB_ID,
    LOCK_ID,
    SETTINGS,
    WAIT_TIMEOUT_SECONDS,
    ManualWaiter,
    acquire_and_lease,
    lock_body,
    running_heartbeat,
    wait_for_heartbeat_thread_to_finish,
)

LEASE_SECONDS = 300
INTERVAL_SECONDS = 100.0
RETRY_SECONDS = 10.0


def lease_text(seconds_after_start: int) -> str:
    return (DEFAULT_NOW + timedelta(seconds=seconds_after_start)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def seed_changed_lock(repository: InMemoryRepository, **overrides: object) -> None:
    """ハートビートが読んだ版の後に、別の書き込みが入る(版が進む)。"""
    repository.seed(LOCK_ID, {**lock_body(repository), **overrides})


# --- 設定 ---


def test_the_default_settings_follow_architecture_11() -> None:
    settings = HeartbeatSettings()

    assert settings.lease_seconds == 300
    assert settings.interval_seconds == 100
    assert settings.retry_interval_seconds < settings.interval_seconds
    assert settings.stop_timeout_seconds > 0


@pytest.mark.parametrize(
    "arguments",
    [
        (300, 100, 100, 30),  # 再試行間隔 = 更新間隔
        (300, 100, 200, 30),  # 再試行間隔 > 更新間隔
        (300, 300, 10, 30),  # 更新間隔 = リース時間
        (100, 200, 10, 30),
        (300, 100, 0, 30),
        (300, 100, 10, 0),  # 停止の待ち
    ],
)
def test_inconsistent_settings_are_rejected(arguments: tuple[float, float, float, float]) -> None:
    with pytest.raises(ValueError):
        HeartbeatSettings(*arguments)


# --- 所有の確認(I/O なし) ---


def test_the_lock_is_owned_while_the_lease_has_not_expired(clock: FixedClock) -> None:
    with running_heartbeat(InMemoryRepository(), clock) as running:
        assert running.heartbeat.is_owned()
        clock.advance(seconds=LEASE_SECONDS - 1)
        assert running.heartbeat.is_owned()


def test_the_lock_is_not_owned_from_the_instant_of_the_last_successful_expiry(
    clock: FixedClock,
) -> None:
    with running_heartbeat(InMemoryRepository(), clock) as running:
        clock.advance(seconds=LEASE_SECONDS)  # 期限ちょうど(以降は所有していない)

        assert not running.heartbeat.is_owned()
        # 喪失は記録していないが、期限で以降の要請を止められる(ハートビートが止まっていても)。
        assert running.heartbeat.lost_reason is None


def test_checking_ownership_does_no_io(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        calls_before = len(repository.behavior.calls)

        for _ in range(5):
            running.heartbeat.is_owned()
        clock.advance(seconds=LEASE_SECONDS + 1)
        running.heartbeat.is_owned()

        assert len(repository.behavior.calls) == calls_before


def test_a_recorded_loss_means_not_owned_even_with_time_left(clock: FixedClock) -> None:
    with running_heartbeat(InMemoryRepository(), clock) as running:
        running.heartbeat.record_loss("lock_not_owned")

        assert not running.heartbeat.is_owned()
        assert running.heartbeat.lost_reason == "lock_not_owned"


def test_the_first_recorded_loss_reason_is_kept(clock: FixedClock) -> None:
    with running_heartbeat(InMemoryRepository(), clock) as running:
        running.heartbeat.record_loss("lock_not_owned")
        running.heartbeat.record_loss("other")

        assert running.heartbeat.lost_reason == "lock_not_owned"


def test_the_lock_can_be_read_only_after_the_heartbeat_started(clock: FixedClock) -> None:
    store = LockStore(InMemoryRepository(), clock)
    heartbeat = Heartbeat(store, clock, SETTINGS, waiter=ManualWaiter())

    with pytest.raises(RuntimeError):
        heartbeat.lock  # noqa: B018 - 開始前の読み取りは誤り


def test_a_heartbeat_cannot_be_started_twice(clock: FixedClock) -> None:
    with running_heartbeat(InMemoryRepository(), clock) as running, pytest.raises(RuntimeError):
        running.heartbeat.start(running.lock, DEFAULT_NOW)


# --- 更新の規則(スレッドなし) ---


def test_a_tick_renews_the_lease_and_returns_the_interval(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        clock.advance(seconds=100)

        next_wait = running.heartbeat.tick()

        assert next_wait == INTERVAL_SECONDS
        assert lock_body(repository)["lease_expires_at"] == lease_text(100 + LEASE_SECONDS)
        assert lock_body(repository)["heartbeat_at"] == lease_text(100)
        # 所有状態に、新しい版と期限が入る(解放は、この版を条件に削除する)。
        assert running.heartbeat.lock.seq_no > running.lock.seq_no
        clock.advance(seconds=LEASE_SECONDS - 1)  # 元の期限(300 秒)は過ぎても、まだ所有している
        assert running.heartbeat.is_owned()


def test_a_tick_writes_only_the_lock_conditioned_on_the_version_it_holds(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        running.heartbeat.tick()
        running.heartbeat.tick()

        assert repository.write_calls() == [ops.CREATE, ops.REPLACE, ops.REPLACE, ops.REPLACE]
        assert repository.record_ids() == [LOCK_ID]


def test_a_store_failure_retries_soon_without_losing_the_lock_before_the_expiry(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        clock.advance(seconds=250)
        repository.behavior.inject(ops.REPLACE, StoreUnavailableError("timeout"))

        next_wait = running.heartbeat.tick()

        assert next_wait == RETRY_SECONDS  # 次の間隔(100 秒)を待たない
        assert running.heartbeat.is_owned()
        assert running.heartbeat.lost_reason is None
        assert lock_body(repository)["lease_expires_at"] == lease_text(
            LEASE_SECONDS
        )  # 書けていない


def test_a_store_failure_after_the_last_successful_expiry_records_a_loss_and_stops(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        repository.behavior.inject(ops.REPLACE, StoreUnavailableError("timeout"), times=None)
        clock.advance(seconds=250)
        assert running.heartbeat.tick() == RETRY_SECONDS
        clock.advance(seconds=60)  # 最後に成功した期限(300 秒)を過ぎた

        next_wait = running.heartbeat.tick()

        assert next_wait is None
        assert running.heartbeat.lost_reason == "lease_expired"
        assert not running.heartbeat.is_owned()


def test_a_store_failure_exactly_at_the_last_successful_expiry_is_a_loss(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        repository.behavior.inject(ops.REPLACE, StoreUnavailableError("timeout"))
        clock.advance(seconds=LEASE_SECONDS)  # 期限ちょうど(Indexer から見て所有していない)

        assert running.heartbeat.tick() is None

        assert running.heartbeat.lost_reason == "lease_expired"


def test_a_failure_to_reread_after_a_conflict_is_a_store_failure(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        seed_changed_lock(repository, heartbeat_at="2026-11-13T00:00:01.000Z")
        repository.behavior.inject(ops.FETCH, StoreUnavailableError("timeout"))

        assert running.heartbeat.tick() == RETRY_SECONDS
        assert running.heartbeat.lost_reason is None


def test_a_conflict_with_our_own_unexpired_lock_is_retried_with_the_reread_version(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        seed_changed_lock(repository, heartbeat_at="2026-11-13T00:00:01.000Z")
        clock.advance(seconds=100)

        next_wait = running.heartbeat.tick()

        assert next_wait == INTERVAL_SECONDS
        assert running.heartbeat.lost_reason is None
        assert lock_body(repository)["lease_expires_at"] == lease_text(100 + LEASE_SECONDS)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"job_id": "job-another"}, "lock_taken_over"),
        ({"owner": "another-crawler"}, "lock_taken_over"),
        ({"lease_expires_at": "2026-11-12T00:00:00.000Z"}, "lease_expired"),
        ({"lease_expires_at": None}, "lease_expired"),
        ({"lease_expires_at": "garbage"}, "lease_expired"),
    ],
)
def test_a_conflict_with_a_lock_that_is_not_ours_or_has_expired_is_a_loss(
    clock: FixedClock, change: Mapping[str, object], reason: str
) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        seed_changed_lock(repository, **change)
        before = repository.body_of(LOCK_ID)

        assert running.heartbeat.tick() is None

        assert running.heartbeat.lost_reason == reason
        assert not running.heartbeat.is_owned()
        assert repository.body_of(LOCK_ID) == before  # 他のジョブのロックを書き換えない


def test_a_vanished_lock_is_a_loss_and_is_not_recreated(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        # 管理者のロック解放が、先にロック文書を削除した(architecture 5.7)。
        repository.delete_ids([LOCK_ID])

        assert running.heartbeat.tick() is None

        assert running.heartbeat.lost_reason == "lock_missing"
        assert repository.body_of(LOCK_ID) is None


@pytest.mark.parametrize(
    "error", [RuntimeError("SECRET-detail"), StoreUnexpectedResponseError("http_400")]
)
def test_an_unexpected_exception_is_recorded_as_a_loss_not_swallowed(
    clock: FixedClock, error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        repository.behavior.inject(ops.REPLACE, error)

        with caplog.at_level(logging.WARNING):
            assert running.heartbeat.tick() is None

        assert running.heartbeat.lost_reason == "unexpected_error"
        assert not running.heartbeat.is_owned()
        assert "SECRET-detail" not in caplog.text  # 例外のメッセージは出さない(R11)
        assert type(error).__name__ in caplog.text


def test_nothing_is_updated_after_a_loss(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        running.heartbeat.record_loss("lock_not_owned")
        calls_before = len(repository.behavior.calls)

        assert running.heartbeat.tick() is None
        assert running.heartbeat.tick() is None

        assert len(repository.behavior.calls) == calls_before
        assert lock_body(repository)["lease_expires_at"] == lease_text(LEASE_SECONDS)


def test_a_loss_is_never_cleared_by_a_later_successful_update(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        seed_changed_lock(repository, job_id="job-another")
        running.heartbeat.tick()
        seed_changed_lock(repository, job_id=JOB_ID)  # 後から自分のロックに戻っても

        assert running.heartbeat.tick() is None

        assert running.heartbeat.lost_reason == "lock_taken_over"
        assert not running.heartbeat.is_owned()


# --- スレッド ---


def test_the_thread_waits_the_interval_renews_and_waits_again(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        running.waiter.wait_until_waiting(1)
        assert running.waiter.requested_waits == [INTERVAL_SECONDS]
        assert lock_body(repository)["lease_expires_at"] == lease_text(LEASE_SECONDS)

        clock.advance(seconds=100)
        running.waiter.release_tick()
        running.waiter.wait_until_waiting(2)

        assert running.waiter.requested_waits == [INTERVAL_SECONDS, INTERVAL_SECONDS]
        assert lock_body(repository)["lease_expires_at"] == lease_text(100 + LEASE_SECONDS)
        assert running.heartbeat.is_owned()


def test_the_lease_is_renewed_while_the_job_thread_is_blocked(clock: FixedClock) -> None:
    """Job Runner が長い呼び出しの中で止まっていても、更新は別のスレッドで続く(#13)。"""
    repository = InMemoryRepository()
    job_is_blocked = threading.Event()
    release_job = threading.Event()
    job_ran = threading.Event()

    with running_heartbeat(repository, clock) as running:

        def job() -> None:
            job_is_blocked.set()
            release_job.wait(WAIT_TIMEOUT_SECONDS)  # Indexer の同期呼び出しなどの待ちを模す
            job_ran.set()

        job_thread = threading.Thread(target=job, daemon=True)
        job_thread.start()
        assert job_is_blocked.wait(WAIT_TIMEOUT_SECONDS)

        running.waiter.wait_until_waiting(1)
        for round_number in range(1, 4):
            clock.advance(seconds=100)
            running.waiter.release_tick()
            running.waiter.wait_until_waiting(round_number + 1)
            assert running.heartbeat.is_owned()

        assert not job_ran.is_set()  # ジョブはまだ止まったまま
        # 元のリース期限(300 秒)を過ぎても、更新されているので所有している。
        assert clock.now() >= DEFAULT_NOW + timedelta(seconds=LEASE_SECONDS)
        assert running.heartbeat.is_owned()

        release_job.set()
        job_thread.join(timeout=WAIT_TIMEOUT_SECONDS)
        assert job_ran.is_set()


def test_the_thread_retries_after_the_short_interval_when_the_update_fails(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        repository.behavior.inject(ops.REPLACE, StoreUnavailableError("timeout"))

        running.waiter.wait_until_waiting(1)
        running.waiter.release_tick()
        running.waiter.wait_until_waiting(2)
        running.waiter.release_tick()
        running.waiter.wait_until_waiting(3)

        assert running.waiter.requested_waits == [INTERVAL_SECONDS, RETRY_SECONDS, INTERVAL_SECONDS]
        assert running.heartbeat.lost_reason is None


def test_the_thread_stops_updating_after_a_loss(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        running.waiter.wait_until_waiting(1)
        seed_changed_lock(repository, job_id="job-another")
        running.waiter.release_tick()

        wait_for_heartbeat_thread_to_finish()  # スレッドは喪失で自分から終わる

        assert running.heartbeat.lost_reason == "lock_taken_over"
        replace_calls = repository.write_calls().count(ops.REPLACE)
        running.waiter.release_tick()  # もう待ちに戻らないので、何も起きない
        assert repository.write_calls().count(ops.REPLACE) == replace_calls
        assert len(running.waiter.requested_waits) == 1


def test_an_unexpected_exception_in_the_thread_is_recorded_as_a_loss(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        repository.behavior.inject(ops.REPLACE, RuntimeError("boom"))
        running.waiter.wait_until_waiting(1)

        running.waiter.release_tick()
        wait_for_heartbeat_thread_to_finish()

        assert running.heartbeat.lost_reason == "unexpected_error"
        assert not running.heartbeat.is_owned()


def test_a_bug_that_escapes_the_tick_is_recorded_as_a_loss_by_the_thread(
    clock: FixedClock, caplog: pytest.LogCaptureFixture
) -> None:
    class BrokenLockStore(LockStore):
        def set_lease(self, *args: Any, **kwargs: Any) -> Any:
            return object()  # `tick` が想定しない結果(不具合の再現)

    repository = InMemoryRepository()
    store = BrokenLockStore(repository, clock)
    leased = acquire_and_lease(LockStore(repository, clock))
    waiter = ManualWaiter()
    heartbeat = Heartbeat(store, clock, SETTINGS, waiter=waiter)
    heartbeat.start(leased.lock, leased.lease_expires_at)
    try:
        waiter.wait_until_waiting(1)
        with caplog.at_level(logging.WARNING):
            waiter.release_tick()
            wait_for_heartbeat_thread_to_finish()

        assert heartbeat.lost_reason == "unexpected_error"
        assert not heartbeat.is_owned()
        assert "thread failed" in caplog.text
    finally:
        heartbeat.stop()


def test_stop_wakes_the_waiting_thread_and_nothing_changes_afterwards(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    with running_heartbeat(repository, clock) as running:
        running.waiter.wait_until_waiting(1)
        body_before = repository.body_of(LOCK_ID)
        lock_before = running.heartbeat.lock

        assert running.heartbeat.stop() is True

        # 解放の後にハートビートが起きても、ロック文書も状態も変えない(#13)。
        assert running.heartbeat.tick() is None
        assert running.heartbeat.tick() is None
        assert repository.body_of(LOCK_ID) == body_before
        assert running.heartbeat.lock == lock_before
        assert running.heartbeat.lost_reason is None


def test_stop_before_start_is_a_no_op(clock: FixedClock) -> None:
    heartbeat = Heartbeat(LockStore(InMemoryRepository(), clock), clock, SETTINGS)

    assert heartbeat.stop() is True


def test_stop_waits_for_the_update_in_progress_and_takes_in_its_version(
    clock: FixedClock,
) -> None:
    update_started = threading.Event()
    let_update_finish = threading.Event()

    class SlowUpdateRepository(InMemoryRepository):
        def __init__(self) -> None:
            super().__init__()
            self.is_slow = False

        def replace_if_unchanged(
            self, record_id: str, body: Mapping[str, Any], *, seq_no: int, primary_term: int
        ) -> ReplaceOutcome:
            if self.is_slow:
                update_started.set()
                let_update_finish.wait(WAIT_TIMEOUT_SECONDS)
            return super().replace_if_unchanged(
                record_id, body, seq_no=seq_no, primary_term=primary_term
            )

    repository = SlowUpdateRepository()
    stop_results: list[bool] = []
    with running_heartbeat(repository, clock) as running:
        running.waiter.wait_until_waiting(1)
        repository.is_slow = True
        running.waiter.release_tick()
        assert update_started.wait(WAIT_TIMEOUT_SECONDS)

        stopper = threading.Thread(
            target=lambda: stop_results.append(running.heartbeat.stop()), daemon=True
        )
        stopper.start()
        let_update_finish.set()
        stopper.join(timeout=WAIT_TIMEOUT_SECONDS)

        assert stop_results == [True]
        # 進行中の更新は完了し、その版が所有状態に入っている(解放はこの版を条件に削除する)。
        assert running.heartbeat.lock.seq_no > running.lock.seq_no
        assert running.heartbeat.lost_reason is None


def test_a_stop_that_times_out_records_a_loss_and_ignores_the_late_result(
    clock: FixedClock,
) -> None:
    update_started = threading.Event()
    let_update_finish = threading.Event()

    class StuckRepository(InMemoryRepository):
        def __init__(self) -> None:
            super().__init__()
            self.is_stuck = False

        def replace_if_unchanged(
            self, record_id: str, body: Mapping[str, Any], *, seq_no: int, primary_term: int
        ) -> ReplaceOutcome:
            if self.is_stuck:
                update_started.set()
                let_update_finish.wait(WAIT_TIMEOUT_SECONDS)
            return super().replace_if_unchanged(
                record_id, body, seq_no=seq_no, primary_term=primary_term
            )

    repository = StuckRepository()
    settings = HeartbeatSettings(
        lease_seconds=300,
        interval_seconds=100,
        retry_interval_seconds=10,
        stop_timeout_seconds=0.05,
    )
    with running_heartbeat(repository, clock, settings) as running:
        running.waiter.wait_until_waiting(1)
        repository.is_stuck = True
        running.waiter.release_tick()
        assert update_started.wait(WAIT_TIMEOUT_SECONDS)
        lock_before = running.heartbeat.lock

        stopped_in_time = running.heartbeat.stop()

        # 待ちの上限を超えた: 喪失として扱う(ロック文書は削除させない = 呼び出し側の規則)。
        assert stopped_in_time is False
        assert running.heartbeat.lost_reason == "stop_timeout"
        assert not running.heartbeat.is_owned()

        let_update_finish.set()
        assert running.heartbeat.stop(timeout_seconds=WAIT_TIMEOUT_SECONDS) is True
        # 遅れて終わった更新の結果は、所有状態に反映しない。
        assert running.heartbeat.lock == lock_before
        assert running.heartbeat.lost_reason == "stop_timeout"
        assert not running.heartbeat.is_owned()


# --- 現行の挙動の固定(設計判断の余地。architecture 5.3 は失敗時の期限超過だけを喪失とする) ---


def test_a_successful_tick_after_the_expiry_makes_the_lock_owned_again(clock: FixedClock) -> None:
    """期限を過ぎて `is_owned()` が False になった後でも、更新に成功すれば True に戻る。

    喪失(`lost_reason`)は、更新の失敗・ロックの消失などで記録したときだけで、時計が期限を
    過ぎたことを観測しても記録・永続化しない(現行の挙動。変えるかは設計判断の余地)。
    確認点(`is_owned()`)が False だった間に Indexer への要請を止めるのは、確認点を通すたびの判定。
    """
    with running_heartbeat(InMemoryRepository(), clock) as running:
        clock.advance(seconds=LEASE_SECONDS + 100)  # スレッドの更新が遅れて、期限を過ぎた
        assert running.heartbeat.is_owned() is False
        assert running.heartbeat.lost_reason is None

        assert running.heartbeat.tick() == INTERVAL_SECONDS

        assert running.heartbeat.is_owned() is True
        assert running.heartbeat.lost_reason is None
