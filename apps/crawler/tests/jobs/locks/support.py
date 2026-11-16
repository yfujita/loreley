"""`jobs/locks` のテストの共通部品。"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from loreley_crawler.jobs.locks import (
    Acquired,
    Heartbeat,
    HeartbeatSettings,
    LeaseSet,
    LockDocument,
    LockStore,
)
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_repository import InMemoryRepository

OWNER = "crawler-1"
JOB_ID = "job-20261113T000000Z-00000001"
SOURCE_ID = "docs"
LOCK_ID = f"lock-{SOURCE_ID}"

# 待ち・合流の上限(不具合で、テストが止まらなくならないように)。
WAIT_TIMEOUT_SECONDS = 5.0

SETTINGS = HeartbeatSettings(
    lease_seconds=300.0,
    interval_seconds=100.0,
    retry_interval_seconds=10.0,
    stop_timeout_seconds=WAIT_TIMEOUT_SECONDS,
)


class ManualWaiter:
    """ハートビートの待ちを、テストが 1 回ずつ進める `TickWaiter`。スリープに頼らない。

    `wait` は、`release_tick` か `stop` が来るまで戻らない。待ちに入ったことと、要求された秒数を
    記録する(`wait_until_waiting` で、スレッドが次の待ちに入った = 1 回の更新が終わったことを確認)。
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._permits = 0
        self._is_stopped = False
        self.requested_waits: list[float] = []

    def wait(self, seconds: float) -> bool:
        with self._condition:
            self.requested_waits.append(seconds)
            self._condition.notify_all()
            released = self._condition.wait_for(
                lambda: self._is_stopped or self._permits > 0, timeout=WAIT_TIMEOUT_SECONDS
            )
            if not released:
                raise AssertionError("the tick was never released")
            if self._is_stopped:
                return True
            self._permits -= 1
            return False

    def stop(self) -> None:
        with self._condition:
            self._is_stopped = True
            self._condition.notify_all()

    def release_tick(self) -> None:
        with self._condition:
            self._permits += 1
            self._condition.notify_all()

    def wait_until_waiting(self, count: int) -> None:
        """スレッドが `count` 回目の待ちに入るまで待つ。"""
        with self._condition:
            reached = self._condition.wait_for(
                lambda: len(self.requested_waits) >= count, timeout=WAIT_TIMEOUT_SECONDS
            )
            assert reached, f"the thread did not reach wait #{count}"


@dataclass
class RunningLock:
    repository: InMemoryRepository
    clock: FixedClock
    store: LockStore
    heartbeat: Heartbeat
    waiter: ManualWaiter
    lock: LockDocument


def acquire_and_lease(store: LockStore) -> LeaseSet:
    acquired = store.acquire(source_id=SOURCE_ID, owner=OWNER, job_id=JOB_ID)
    assert isinstance(acquired, Acquired)
    leased = store.set_lease(
        acquired.lock, lease_seconds=SETTINGS.lease_seconds, require_active_lease=False
    )
    assert isinstance(leased, LeaseSet)
    return leased


@contextmanager
def running_heartbeat(
    repository: InMemoryRepository, clock: FixedClock, settings: HeartbeatSettings = SETTINGS
) -> Iterator[RunningLock]:
    """ロックを取得してリースを設定し、ハートビートを始める。抜けるときに必ず止める。"""
    store = LockStore(repository, clock)
    leased = acquire_and_lease(store)
    waiter = ManualWaiter()
    heartbeat = Heartbeat(store, clock, settings, waiter=waiter)
    heartbeat.start(leased.lock, leased.lease_expires_at)
    try:
        yield RunningLock(repository, clock, store, heartbeat, waiter, leased.lock)
    finally:
        heartbeat.stop()


def lock_body(repository: InMemoryRepository) -> dict[str, Any]:
    body = repository.body_of(LOCK_ID)
    assert body is not None
    return body


def wait_for_heartbeat_thread_to_finish() -> None:
    """喪失などでスレッドが自分から終わるのを待つ(`stop()` を先に呼ぶと、停止が結果を変える)。"""
    for thread in threading.enumerate():
        if thread.name == "lease-heartbeat":
            thread.join(timeout=WAIT_TIMEOUT_SECONDS)
            assert not thread.is_alive()
