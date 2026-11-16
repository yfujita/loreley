"""ハートビート: 実行中のジョブのロック文書のリースを、専用スレッドで更新する(module 2.2・5.4。
architecture 5.3・5.5・5.7。CM-P-14)。

ジョブ実行とは独立に動く。Job Runner のスレッドが Connector・Indexer の同期呼び出し・待ちの中に
いても、更新は別のスレッドで続き、リースは切れない。**専用の Store 層のクライアント**(別の短い
タイムアウト)につないだ `LockStore` を使うこと。

- **所有状態をメモリ上に持つ**: 最後の版・最後に成功した更新のリース期限・喪失の有無。
  Job Runner は、Indexer への要請の前に `is_owned()` で確認する。I/O をせず、この状態と
  時計だけで答える。
  「所有していない」のは、(a) 喪失を記録している、または (b) 現在時刻が最後に成功した更新の
  リース期限以降のとき(ハートビートが止まっても、リース切れで以降の要請を止められる)。
- **喪失の記録**: 更新の失敗が続いて期限を過ぎた・ロック文書の消失・他のジョブのロック・
  期限切れ・想定外の例外(握りつぶさず、喪失として記録して止まる)。`lock_not_owned` を受けた
  実行対象も `record_loss` で記録する(`JobContext` 経由)。**喪失の後は更新しない。**
- **停止**: `stop()` が進行中の更新の完了を待つ。待ちの上限を超えたら喪失として記録し
  (以後の更新結果は状態に反映しない)、`False` を返す。呼び出し側(Job Runner)は、喪失を
  記録している間はロック文書を削除しない(architecture 5.7)。停止した後は、ロック文書も
  状態も変えない。
- 時間の流れは `TickWaiter`(待ち)と `Clock` で差し替えられる。テストは、`tick()` を直接呼んで
  更新の規則を確かめ、スレッドのテストは待ちを手動で進める(スリープに頼らない)。
"""

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from loreley_crawler.common.clock import Clock
from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.jobs.locks.lock_document import LockDocument
from loreley_crawler.jobs.locks.lock_store import LeaseResult, LockNotOwned, LockStore

logger = logging.getLogger(__name__)

LOSS_LEASE_EXPIRED = "lease_expired"
LOSS_UNEXPECTED_ERROR = "unexpected_error"
LOSS_STOP_TIMEOUT = "stop_timeout"


@dataclass(frozen=True)
class HeartbeatSettings:
    """秒数の仮値(architecture 11章・module CM-U-6。設定可能)。

    再試行間隔 < 更新間隔 < リース時間。停止の待ちの上限は、ハートビート専用クライアントの
    タイムアウト以上(更新 1 回 + 読み直し 1 回ぶん)にする(整合性は `config.py` が検査する)。
    """

    lease_seconds: float = 300.0
    interval_seconds: float = 100.0
    retry_interval_seconds: float = 10.0
    stop_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not 0 < self.retry_interval_seconds < self.interval_seconds < self.lease_seconds:
            raise ValueError("require 0 < retry_interval < interval < lease")
        if self.stop_timeout_seconds <= 0:
            raise ValueError("stop_timeout_seconds must be positive")


class TickWaiter(Protocol):
    def wait(self, seconds: float) -> bool:
        """`seconds` 待つ。停止が要求されたら(待ちの途中でも)すぐ戻り、True を返す。"""
        ...

    def stop(self) -> None:
        """待ちを打ち切らせ、以後の `wait` が True を返すようにする。"""
        ...


class EventTickWaiter:
    def __init__(self) -> None:
        self._stop_requested = threading.Event()

    def wait(self, seconds: float) -> bool:
        return self._stop_requested.wait(seconds)

    def stop(self) -> None:
        self._stop_requested.set()


class Heartbeat:
    """1 つのジョブの実行の間だけ動く。`start` → `is_owned`・`record_loss` → `stop`。"""

    def __init__(
        self,
        lock_store: LockStore,
        clock: Clock,
        settings: HeartbeatSettings,
        *,
        waiter: TickWaiter | None = None,
    ) -> None:
        self._lock_store = lock_store
        self._clock = clock
        self._settings = settings
        self._waiter = waiter or EventTickWaiter()
        self._thread: threading.Thread | None = None
        # 所有状態。ハートビートのスレッドと Job Runner が共有するので、`_state_lock` で守る。
        self._state_lock = threading.Lock()
        self._lock: LockDocument | None = None
        self._lease_expires_at: datetime | None = None
        self._lost_reason: str | None = None
        self._is_stopped = False
        self._is_abandoned = False

    def start(self, lock: LockDocument, lease_expires_at: datetime) -> None:
        """リース設定(`LockStore.set_lease`)で得た版と期限で、更新のスレッドを始める。"""
        if self._thread is not None:
            raise RuntimeError("heartbeat is already started")
        with self._state_lock:
            self._lock = lock
            self._lease_expires_at = lease_expires_at
        self._thread = threading.Thread(target=self._run, name="lease-heartbeat", daemon=True)
        self._thread.start()

    def is_owned(self) -> bool:
        """所有の確認(I/O なし。Indexer への要請の前に呼ぶ)。"""
        with self._state_lock:
            return (
                self._lost_reason is None
                and self._lease_expires_at is not None
                and self._clock.now() < self._lease_expires_at
            )

    @property
    def lost_reason(self) -> str | None:
        with self._state_lock:
            return self._lost_reason

    @property
    def lock(self) -> LockDocument:
        """最後に更新に成功したロック文書(解放の削除の版)。`start` の後に読む。"""
        with self._state_lock:
            if self._lock is None:
                raise RuntimeError("heartbeat is not started")
            return self._lock

    def record_loss(self, reason: str) -> None:
        """所有権の喪失を記録する(`lock_not_owned` を受けた実行対象など)。最初の理由を保つ。"""
        with self._state_lock:
            self._record_loss_locked(reason)

    def stop(self, *, timeout_seconds: float | None = None) -> bool:
        """更新を止め、進行中の更新の完了を待つ。上限内に止まれば True。

        上限(既定は `stop_timeout_seconds`)を超えたら喪失(`stop_timeout`)として記録し、
        以後の更新結果は状態に反映しない。`timeout_seconds` は、待ち直すテスト用の指定。
        """
        with self._state_lock:
            self._is_stopped = True
        self._waiter.stop()
        thread = self._thread
        if thread is None:
            return True
        thread.join(
            timeout=self._settings.stop_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )
        if not thread.is_alive():
            return True
        with self._state_lock:
            self._is_abandoned = True
            self._record_loss_locked(LOSS_STOP_TIMEOUT)
        return False

    def tick(self) -> float | None:
        """リースの更新を 1 回試み、次の更新までの待ち秒数を返す。None はこれ以上更新しない。

        スレッドのループが呼ぶ。止めた後・喪失の後は、何もせず None を返す。
        """
        with self._state_lock:
            if self._is_stopped or self._lost_reason is not None or self._lock is None:
                return None
            lock = self._lock
        try:
            result = self._lock_store.set_lease(
                lock, lease_seconds=self._settings.lease_seconds, require_active_lease=True
            )
        except StoreUnavailableError:
            return self._after_failed_update()
        except Exception as error:
            # 想定外の例外(`StoreUnexpectedResponseError` を含む)。握りつぶさず、喪失として
            # 記録する。例外のメッセージは出さない(R11)。
            logger.warning(
                "heartbeat stopped by an unexpected error: error=%s", type(error).__name__
            )
            self.record_loss(LOSS_UNEXPECTED_ERROR)
            return None
        return self._apply(result)

    def _apply(self, result: LeaseResult) -> float | None:
        with self._state_lock:
            if self._is_abandoned:
                return None  # 停止の待ちを超えた。以後の結果は状態に反映しない
            if isinstance(result, LockNotOwned):
                self._record_loss_locked(result.reason)
                return None
            self._lock = result.lock
            self._lease_expires_at = result.lease_expires_at
            return None if self._is_stopped else self._settings.interval_seconds

    def _after_failed_update(self) -> float | None:
        """書き込みの失敗: 次の間隔を待たず、短い間隔でやり直す。期限を過ぎたら喪失。"""
        with self._state_lock:
            if self._is_abandoned:
                return None
            if self._lease_expires_at is None or self._clock.now() >= self._lease_expires_at:
                self._record_loss_locked(LOSS_LEASE_EXPIRED)
                return None
            return self._settings.retry_interval_seconds

    def _record_loss_locked(self, reason: str) -> None:
        if self._lost_reason is None:
            self._lost_reason = reason

    def _run(self) -> None:
        next_wait_seconds: float | None = self._settings.interval_seconds
        try:
            while next_wait_seconds is not None:
                if self._waiter.wait(next_wait_seconds):
                    return  # 停止が要求された
                next_wait_seconds = self.tick()
        except Exception as error:
            # `tick` が捕捉しない想定外(不具合)。スレッドが黙って死なないよう、喪失を記録する。
            logger.warning("heartbeat thread failed: error=%s", type(error).__name__)
            self.record_loss(LOSS_UNEXPECTED_ERROR)
