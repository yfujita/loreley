"""ロック解放(管理者)(architecture 5.4。crawler-api 4.3)。

実行中でないロックだけを解放する。判定(解放しないものは `LockInUse` で拒否し、何も書かない):

| ロック文書の状態 | 結果 |
| --- | --- |
| ロック文書がない | 何もしない(`NoLockToRelease`) |
| ジョブ記録がなく、`acquired_at` が直近でない(孤児ロック) | 解放する |
| ジョブ記録がなく、`acquired_at` が直近(受付の途中の可能性) | 解放しない |
| ジョブが終端状態(孤児ロック) | 解放する |
| ジョブが `queued`(`crawl` は取り消しを使う) | 解放しない |
| ジョブが `running` で、リース期限内 | 解放しない(`lock_in_use`) |
| ジョブが `running` で、リース切れ(null・形式不正を含む) | 解放し、ジョブを `failed` にする |

**順序**: ロック文書の削除(読んだ版を条件)が先、ジョブの `failed` が後。リースの更新が再開して
いれば版が進んで削除の条件が外れ、読み直して判定し直す(生きているジョブを `failed` にしない)。
ロックの削除の後でジョブの更新が競合しても、ロックのない `running` のジョブは所有を失っているので、
`running` なら読み直した版で `failed` にする。Job Runner の更新が先に入っていた場合に、
Job Runner が `failed`(`lock_released`)を読んで所有権の喪失として止まるのは `JobContext` の側。

ジョブ記録の状態が形式不正で読めないときは、実行中でないと判断できないので解放しない(`LockInUse`。
`existing_job.status` は None)。

繰り返しても競合が解けなければ `StoreUnavailableError`(503)。
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto

from loreley_crawler.common.clock import Clock
from loreley_crawler.common.conflict import MAX_CONFLICT_ATTEMPTS
from loreley_crawler.common.errors import (
    StoreUnavailableError,
    StoreUnexpectedResponseError,
    is_store_unavailable,
)
from loreley_crawler.common.retry import Retrier
from loreley_crawler.common.timestamps import format_instant
from loreley_crawler.jobs.existing_job import ExistingJob, describe_existing_job
from loreley_crawler.jobs.job_updates import Applied, apply_job_update
from loreley_crawler.jobs.locks import LockDeleted, LockDocument, LockStore
from loreley_crawler.jobs.log_text import loggable_id
from loreley_crawler.jobs.records import FailureReason, JobRecord, JobRecordStore, JobStatus
from loreley_crawler.jobs.settings import JobsSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NoLockToRelease:
    """ロック文書がない(200 `released=false`)。"""


@dataclass(frozen=True)
class LockReleased:
    """ロック文書を削除した(200 `released=true`)。

    `failed_job_id` は、`failed`(`lock_released`)にした `running` のジョブ(なければ None)。
    """

    failed_job_id: str | None


@dataclass(frozen=True)
class LockInUse:
    """解放しないロック(409 `lock_in_use`)。"""

    existing_job: ExistingJob


ReleaseLockResult = NoLockToRelease | LockReleased | LockInUse


class _Verdict(Enum):
    IN_USE = auto()
    RELEASE = auto()
    RELEASE_AND_FAIL_JOB = auto()


class LockRelease:
    def __init__(
        self,
        *,
        settings: JobsSettings,
        job_store: JobRecordStore,
        lock_store: LockStore,
        clock: Clock,
        retrier: Retrier,
    ) -> None:
        self._admitting_lock_grace = timedelta(seconds=settings.admitting_lock_grace_seconds)
        self._job_store = job_store
        self._lock_store = lock_store
        self._clock = clock
        self._retrier = retrier

    def release(self, source_id: str) -> ReleaseLockResult:
        for _ in range(MAX_CONFLICT_ATTEMPTS):
            result = self._release_once(source_id)
            if result is not None:
                return result
        raise StoreUnavailableError("lock_release_contention")

    def _release_once(self, source_id: str) -> ReleaseLockResult | None:
        """読んで判定し、解放する。ロックの版が外れたら None(呼び出し側が読み直す)。"""
        lock = self._retrier.run(
            lambda: self._lock_store.read(source_id), is_retryable_error=is_store_unavailable
        )
        if lock is None:
            return NoLockToRelease()
        job = self._retrier.run(
            lambda: self._job_store.fetch(lock.job_id), is_retryable_error=is_store_unavailable
        )
        try:
            verdict = self._judge(lock, job)
        except StoreUnexpectedResponseError as error:
            if error.error_type != "malformed_job_record":
                raise
            # ジョブの状態が読めないので、実行中でないと判断できない。解放しない(安全側)。
            return LockInUse(describe_existing_job(lock, job))
        if verdict is _Verdict.IN_USE:
            return LockInUse(describe_existing_job(lock, job))
        return self._delete(lock, job, verdict)

    def _judge(self, lock: LockDocument, job: JobRecord | None) -> _Verdict:
        now = self._clock.now()
        if job is None:
            return _Verdict.IN_USE if self._is_admitting(lock, now) else _Verdict.RELEASE
        status = job.status
        if status.is_terminal:
            return _Verdict.RELEASE
        if status is JobStatus.QUEUED or lock.has_active_lease(now):
            return _Verdict.IN_USE
        return _Verdict.RELEASE_AND_FAIL_JOB

    def _is_admitting(self, lock: LockDocument, now: datetime) -> bool:
        """受付の途中のロックか(`acquired_at` が直近)。読めない `acquired_at` は十分に古い。"""
        return now - lock.acquired_at < self._admitting_lock_grace

    def _delete(
        self, lock: LockDocument, job: JobRecord | None, verdict: _Verdict
    ) -> ReleaseLockResult | None:
        """ロック文書を消す。版が外れたら None(読み直して判定し直す)。"""
        deleted = self._retrier.run(
            lambda: self._lock_store.delete_unchanged(lock), is_retryable_error=is_store_unavailable
        )
        if not isinstance(deleted, LockDeleted) and not self._is_gone(lock):
            return None
        if verdict is _Verdict.RELEASE_AND_FAIL_JOB and job is not None:
            return LockReleased(self._fail_job_logging_failure(job))
        return LockReleased(None)

    def _is_gone(self, lock: LockDocument) -> bool:
        """版が外れたとき、ロック文書がなくなっているか(応答が失われた削除の成功を含む)。"""
        reread = self._retrier.run(
            lambda: self._lock_store.read(lock.source_id), is_retryable_error=is_store_unavailable
        )
        return reread is None

    def _fail_job_logging_failure(self, job: JobRecord) -> str | None:
        """ロックを削除した後のジョブの更新が、Store 層の異常で失敗したときは、警告して送出する。

        ロックのない `running` のジョブが残る(次の起動時の回復が `failed` にする)ので、
        どのジョブか分かるように残す。
        """
        try:
            return self._fail_job(job)
        except StoreUnavailableError:
            logger.warning(
                "the lock was released but the running job could not be failed: job_id=%s",
                loggable_id(job.job_id),
            )
            raise

    def _fail_job(self, job: JobRecord) -> str | None:
        """`running` のジョブを `failed`(`lock_released`)にする。すでに終端などなら何もしない。"""
        outcome = apply_job_update(
            self._job_store,
            self._retrier,
            job,
            {
                "status": JobStatus.FAILED.value,
                "failure_reason": FailureReason.LOCK_RELEASED.value,
                "finished_at": format_instant(self._clock.now()),
            },
            applicable_statuses=[JobStatus.RUNNING],
        )
        return job.job_id if isinstance(outcome, Applied) else None
