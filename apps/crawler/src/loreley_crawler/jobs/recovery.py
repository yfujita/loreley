"""Crawler 起動時の回復(architecture 5.8。module 5.7)。

受付・Job Runner・Scheduler を始める前に、1 度だけ行う。他の書き手がいないので競合しない。
対象は `owner` が自分のロックと、そのジョブだけ。

1. `running` のジョブを `failed`(`crawler_restart`)にする。登録結果は最後に記録した値のまま。
   終了通知は送らない(確認結果の区分も書かない)。
2. 終端状態のジョブのロック、ジョブ記録のないロック(孤児ロック)、手順 1 で `failed` にしたジョブの
   ロックを、読んだ版を条件に削除する。
3. `queued` のジョブは、そのまま残す(ロックも保持。Job Runner が `queued_at` の順に実行する)。
4. `owner` が自分以外のロックは触らず、警告をログに出す(単一 Crawler では起きない)。

判断できないものは触らない(保守側): ジョブが `running` のまま残るロック(手順 1 の後は、`owner` が
自分以外のジョブのときだけ)は削除しない。
"""

import logging
from dataclasses import dataclass

from loreley_crawler.common.clock import Clock
from loreley_crawler.common.errors import StoreUnexpectedResponseError, is_store_unavailable
from loreley_crawler.common.retry import Retrier
from loreley_crawler.common.timestamps import format_instant
from loreley_crawler.jobs.job_updates import Applied, apply_job_update
from loreley_crawler.jobs.lock_cleanup import delete_lock_unless_taken_over
from loreley_crawler.jobs.locks import LockDocument, LockStore
from loreley_crawler.jobs.log_text import loggable_id
from loreley_crawler.jobs.records import FailureReason, JobRecordStore, JobStatus
from loreley_crawler.jobs.settings import JobsSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecoveryReport:
    """回復で行ったこと(ログと検証用)。"""

    failed_job_ids: tuple[str, ...]
    deleted_lock_source_ids: tuple[str, ...]
    # 削除しなかったロック: `queued` のジョブのロック(実行される)、`owner` が自分以外のロック、
    # 判断できないロック。
    kept_lock_source_ids: tuple[str, ...]


class StartupRecovery:
    def __init__(
        self,
        *,
        settings: JobsSettings,
        job_store: JobRecordStore,
        lock_store: LockStore,
        clock: Clock,
        retrier: Retrier,
    ) -> None:
        self._owner = settings.owner
        self._job_store = job_store
        self._lock_store = lock_store
        self._clock = clock
        self._retrier = retrier

    def run(self) -> RecoveryReport:
        failed_job_ids = self._fail_running_jobs()
        locks = self._retrier.run(
            self._lock_store.list_locks, is_retryable_error=is_store_unavailable
        )
        deleted: list[str] = []
        kept: list[str] = []
        for lock in locks:
            if self._is_stale(lock):
                self._delete_lock(lock)
                deleted.append(lock.source_id)
            else:
                kept.append(lock.source_id)
        return RecoveryReport(tuple(failed_job_ids), tuple(deleted), tuple(kept))

    def _fail_running_jobs(self) -> list[str]:
        running_jobs = self._retrier.run(
            lambda: self._job_store.list_running(self._owner),
            is_retryable_error=is_store_unavailable,
        )
        failed_job_ids: list[str] = []
        for job in running_jobs:
            outcome = apply_job_update(
                self._job_store,
                self._retrier,
                job,
                {
                    "status": JobStatus.FAILED.value,
                    "failure_reason": FailureReason.CRAWLER_RESTART.value,
                    "finished_at": format_instant(self._clock.now()),
                },
                applicable_statuses=[JobStatus.RUNNING],
            )
            if isinstance(outcome, Applied):
                failed_job_ids.append(job.job_id)
        return failed_job_ids

    def _is_stale(self, lock: LockDocument) -> bool:
        """削除してよいロックか: 自分のロックで、ジョブ記録がない、またはジョブが終端状態。

        `queued` のジョブのロックは残す(実行される)。`owner` が自分以外のロック、`running` の
        ジョブのロック(手順 1 の後に残るのは、`owner` が自分以外のジョブだけ)、ジョブ記録の
        `status` が形式不正なロックは、判断できないので触らず、警告する(回復は続ける)。

        手順 1(`running` のジョブ)は、`status` が `running` と書かれた記録だけを対象にし、
        `job_type`・`source_id` などは読まないので、他の項目の形式不正では止まらない。
        """
        if lock.owner != self._owner:
            logger.warning(
                "found a lock owned by another crawler (left untouched): source_id=%s",
                loggable_id(lock.source_id),
            )
            return False
        job = self._retrier.run(
            lambda: self._job_store.fetch(lock.job_id), is_retryable_error=is_store_unavailable
        )
        if job is None:
            return True
        try:
            status = job.status
        except StoreUnexpectedResponseError as error:
            if error.error_type != "malformed_job_record":
                raise
            # 状態が読めないので、終端と判断できない。ロックも記録も触らず、回復を続ける
            # (回復全体を止めると、管理者の解放も再起動もできなくなる)。
            logger.warning(
                "found a lock of a job with an unreadable status (left untouched): "
                "source_id=%s job_id=%s",
                loggable_id(lock.source_id),
                loggable_id(lock.job_id),
            )
            return False
        if status is JobStatus.RUNNING:
            logger.warning(
                "found a lock of a running job that is not ours (left untouched): source_id=%s",
                loggable_id(lock.source_id),
            )
        return status.is_terminal

    def _delete_lock(self, lock: LockDocument) -> None:
        self._retrier.run(
            lambda: delete_lock_unless_taken_over(
                self._lock_store,
                lock,
                is_target=lambda current: current.is_held_by(lock.owner, lock.job_id),
            ),
            is_retryable_error=is_store_unavailable,
        )
