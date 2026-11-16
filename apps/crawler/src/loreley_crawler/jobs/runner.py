"""Job Runner: `queued` のジョブを `queued_at` の順に 1 件ずつ実行する(module 4.4・5.2・2.2)。

1 件のジョブの流れ(architecture 4.5 の手順 6 の最初の段、5.3・5.5・5.7):
1. ロック文書のリースを設定する(所有の確認を兼ねる)。ロックがない・他のジョブのものなら、実行せず
   ジョブを `failed`(`lock_lost`)にする(`queued` から直接。実行を始められなかったため)。
2. ハートビートを始め、`job_type` に対応する**実行対象**を呼ぶ。実行対象は `main.py` から注入され、
   `crawl`・`source_delete` を import しない(R3)。実行対象は `JobContext` を通して、`running` への
   遷移から最終状態の記録までを行う。`queued` -> `running` で取り消しに負けたとき
   (`JobNotStartable`)は、実行せずに止まる。
3. **実行対象の終わり方を問わず 1 回**、ハートビートを止め、ロック文書を削除する(解放)。
   - 所有権の喪失を記録しているとき、ハートビートの停止の待ちが上限を超えたとき(喪失として
     扱う)は、ロック文書が自分の `owner`・`job_id` のままでも削除しない(保守側。回復か管理者の
     解放に委ねる)。
   - 最終状態を記録できていないときも削除しない(`running` のジョブのロックを消して、受付を
     通してしまわないため。リースが切れた後、管理者の解放が `failed`(`lock_released`)にする)。
4. **最後の手段**: 実行対象が最終状態を記録しないまま終わった(例外を送出した、または返った)ときだけ
   `failed` を記録してから解放する。理由は、Store 層の異常(`StoreUnavailableError`)なら
   `store_unavailable`、それ以外は `internal_error`。想定外の例外の捕捉と終了通知の試みは、
   まず実行対象が行う(`crawl`)。

起床通知(`RunnerWakeup`)か走査間隔で動く。1 回の走査の失敗(Store 層の異常など)でスレッドを
終わらせず、次の走査で再試行する。ログには例外の種類だけを出す(R11)。
"""

import logging
import threading
from collections.abc import Callable, Mapping

from loreley_crawler.common.clock import Clock
from loreley_crawler.common.errors import StoreUnavailableError, is_store_unavailable
from loreley_crawler.common.retry import Retrier
from loreley_crawler.common.timestamps import format_instant
from loreley_crawler.jobs.cancel_requests import CancelRequestRegistry
from loreley_crawler.jobs.context import JobContext
from loreley_crawler.jobs.interruptions import JobNotStartable
from loreley_crawler.jobs.job_updates import Applied, apply_job_update
from loreley_crawler.jobs.locks import Heartbeat, LeaseSet, LockNotOwned, LockStore, NotReleased
from loreley_crawler.jobs.log_text import loggable_id
from loreley_crawler.jobs.records import (
    FailureReason,
    JobRecord,
    JobRecordStore,
    JobStatus,
    JobType,
)
from loreley_crawler.jobs.settings import JobsSettings
from loreley_crawler.jobs.wakeup import RunnerWakeup

logger = logging.getLogger(__name__)

# 実行対象: ジョブ記録(`queued`)と `JobContext` を受けて、最終状態の記録までを行う。
JobExecutor = Callable[[JobRecord, JobContext], None]


class JobRunner:
    def __init__(
        self,
        *,
        settings: JobsSettings,
        job_store: JobRecordStore,
        lock_store: LockStore,
        heartbeat_factory: Callable[[], Heartbeat],
        executors: Mapping[JobType, JobExecutor],
        cancel_requests: CancelRequestRegistry,
        wakeup: RunnerWakeup,
        read_maintenance_flag: Callable[[], bool],
        clock: Clock,
        retrier: Retrier,
        stop_requested: threading.Event | None = None,
    ) -> None:
        if set(executors) != set(JobType):
            raise ValueError("an executor is required for every job type")
        self._settings = settings
        self._owner = settings.owner
        self._job_store = job_store
        self._lock_store = lock_store
        self._heartbeat_factory = heartbeat_factory
        self._executors = dict(executors)
        self._cancel_requests = cancel_requests
        self._wakeup = wakeup
        self._read_maintenance_flag = read_maintenance_flag
        self._clock = clock
        self._retrier = retrier
        self._stop_requested = stop_requested or threading.Event()
        self._thread: threading.Thread | None = None

    # --- スレッドの開始・停止 ---

    def start(self) -> None:
        """専用のスレッド(daemon)で `run_until_stopped` を始める。"""
        if self._thread is not None:
            raise RuntimeError("the job runner is already started")
        self._thread = threading.Thread(
            target=self.run_until_stopped, name="job-runner", daemon=True
        )
        self._thread.start()

    def request_stop(self) -> None:
        """停止を要求する。実行中のジョブの完了は待たない(CM-U-4。次回の回復に委ねる)。"""
        self._stop_requested.set()
        self._wakeup.notify()

    def join(self, timeout_seconds: float) -> bool:
        """スレッドの終了を `timeout_seconds` まで待つ。終わっていれば True。"""
        if self._thread is None:
            return True
        self._thread.join(timeout=timeout_seconds)
        return not self._thread.is_alive()

    def run_until_stopped(self) -> None:
        while not self._stop_requested.is_set():
            try:
                ran = self.run_next()
            except Exception as error:
                # 次の走査で再試行する(ジョブは `queued` のまま残る)。例外の種類だけを出す。
                logger.warning("job runner iteration failed: error=%s", type(error).__name__)
                ran = False
            if not ran:
                self._wakeup.wait(self._settings.runner_scan_interval_seconds)

    # --- 1 件の実行 ---

    def run_next(self) -> bool:
        """`queued_at` が最も古い `queued` のジョブを 1 件実行する。

        ジョブを終端にできたら True(続けて次の走査をしてよい)。`queued` がない、または
        ジョブを終端にできなかった(Store 層の異常など。ジョブは `queued`・`running` のまま)
        ときは False(呼び出し側が、走査間隔だけ待つ。同じジョブを待たずに繰り返さないため)。
        """
        record = self._retrier.run(
            lambda: self._job_store.find_oldest_queued(self._owner),
            is_retryable_error=is_store_unavailable,
        )
        if record is None:
            return False
        try:
            return self._run_job(record)
        except Exception as error:
            logger.warning(
                "job runner failed to run a job: job_id=%s error=%s",
                loggable_id(record.job_id),
                type(error).__name__,
            )
            return False

    def _run_job(self, record: JobRecord) -> bool:
        """ジョブを実行する。ジョブが終端になった(または、他者が終端にしていた)ら True。"""
        executor = self._executors[record.job_type]
        leased = self._set_lease(record)
        if leased is None:
            return True  # ジョブを `failed` にした(または、すでに `queued` でなかった)
        heartbeat = self._heartbeat_factory()
        context = JobContext(
            record=record,
            job_store=self._job_store,
            heartbeat=heartbeat,
            cancel_requests=self._cancel_requests,
            read_maintenance_flag=self._read_maintenance_flag,
            clock=self._clock,
            retrier=self._retrier,
        )
        try:
            heartbeat.start(leased.lock, leased.lease_expires_at)
            self._execute(executor, record, context)
        finally:
            self._release(record, context, heartbeat)
        return context.is_terminal

    def _set_lease(self, record: JobRecord) -> LeaseSet | None:
        """リースを設定する。ロックを失っていて実行できないときは、ジョブを `failed` にし None。"""
        lock = self._retrier.run(
            lambda: self._lock_store.read(record.source_id), is_retryable_error=is_store_unavailable
        )
        if lock is None or not lock.is_held_by(self._owner, record.job_id):
            self._fail_unstartable_job(record)
            return None
        result = self._retrier.run(
            lambda: self._lock_store.set_lease(
                lock,
                lease_seconds=self._settings.heartbeat.lease_seconds,
                require_active_lease=False,
            ),
            is_retryable_error=is_store_unavailable,
        )
        if isinstance(result, LockNotOwned):
            self._fail_unstartable_job(record)
            return None
        return result

    def _fail_unstartable_job(self, record: JobRecord) -> None:
        """ロックを失った `queued` のジョブは、実行しない(所有なしに Indexer を呼ばない)。

        取り消しなどで、すでに `queued` でなければ何もしない。
        """
        outcome = apply_job_update(
            self._job_store,
            self._retrier,
            record,
            {
                "status": JobStatus.FAILED.value,
                "failure_reason": FailureReason.LOCK_LOST.value,
                "finished_at": format_instant(self._clock.now()),
            },
            applicable_statuses=[JobStatus.QUEUED],
        )
        if isinstance(outcome, Applied):
            logger.warning(
                "a queued job lost its lock before it started (failed): job_id=%s",
                loggable_id(record.job_id),
            )

    def _execute(self, executor: JobExecutor, record: JobRecord, context: JobContext) -> None:
        try:
            executor(record, context)
        except JobNotStartable:
            return  # 取り消しに負けた。ジョブはすでに終端で、ここで記録するものはない
        except Exception as error:
            logger.warning(
                "an executor ended with an unexpected error: job_id=%s error=%s",
                loggable_id(record.job_id),
                type(error).__name__,
            )
            # 最終状態を記録した後の例外は、記録済みの最終状態を変えない。
            if not context.is_terminal:
                self._record_last_resort(context, error)
            return
        if not context.is_terminal:
            logger.warning(
                "an executor returned without recording a final state: job_id=%s",
                loggable_id(record.job_id),
            )
            self._record_last_resort(context, None)

    def _record_last_resort(self, context: JobContext, error: Exception | None) -> None:
        reason = (
            FailureReason.STORE_UNAVAILABLE
            if isinstance(error, StoreUnavailableError)
            else FailureReason.INTERNAL_ERROR
        )
        try:
            context.finish(JobStatus.FAILED, failure_reason=reason)
        except Exception as finish_error:
            # 記録できなかった。ロックは削除しない(`_release`)。
            logger.warning(
                "could not record the last-resort failure: job_id=%s error=%s",
                loggable_id(context.job_id),
                type(finish_error).__name__,
            )

    def _release(self, record: JobRecord, context: JobContext, heartbeat: Heartbeat) -> None:
        """実行対象の終わり方を問わず、1 回行う。ハートビートを止めてから、ロック文書を削除する。"""
        try:
            is_stopped = heartbeat.stop()
        finally:
            self._cancel_requests.clear(record.job_id)
        lost_reason = heartbeat.lost_reason
        if not is_stopped or lost_reason is not None:
            logger.warning(
                "the lock is kept because ownership may be lost: job_id=%s reason=%s",
                loggable_id(record.job_id),
                lost_reason,
            )
            return
        if not context.is_terminal:
            logger.warning(
                "the lock is kept because no final state was recorded: job_id=%s",
                loggable_id(record.job_id),
            )
            return
        try:
            released = self._retrier.run(
                lambda: self._lock_store.release_own(heartbeat.lock),
                is_retryable_error=is_store_unavailable,
            )
            if isinstance(released, NotReleased):
                # 他のジョブのロックになっていたので、消していない(理由は固定の名前)。
                logger.warning(
                    "the lock was not released: job_id=%s reason=%s",
                    loggable_id(record.job_id),
                    released.reason,
                )
        except Exception as error:
            # 終端のジョブのロックが残る(孤児ロック)。起動時の回復か、管理者の解放が消す。
            logger.warning(
                "failed to release the lock (an orphan lock remains): job_id=%s error=%s",
                loggable_id(record.job_id),
                type(error).__name__,
            )
