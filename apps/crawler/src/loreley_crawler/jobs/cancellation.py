"""取り消し(architecture 4.7。crawler-api 4.2。module 5.5)。

`crawl` ジョブだけが対象(`source_delete` は取り消さず、再実行で復旧する)。判定の順序は
crawler-api 4.2: ジョブがない(404)→ `source_delete`(409 `job_not_cancellable`。状態を問わない)
→ 終端状態(409 `job_already_finished`)→ 状態別の扱い。

- `queued`: 読んだ版を条件に `cancelled` にし、そのジョブのロックを解放する。Job Runner の
  `queued` -> `running` と競合したら、先に条件付き更新に勝った側が有効。負けたら読み直し、
  `running` なら取り消し要求を伝える(202)。
  **既知の限界**: `cancelled` にした後のロックの削除が Store 層の異常で失敗すると、その呼び出しは
  503 になり、再試行は `JobAlreadyFinished`(409)になる。ロック文書は終端のジョブの孤児ロックとして
  残り、管理者の解放か再起動時の回復が消す(architecture 5.5 が許容する)。
- `running`: 取り消し要求をメモリ上のレジストリに記録する(ジョブ記録は書かない)。確認点で、
  実行対象が反映する。メンテナンスフラグは確認しない(CAPI-P-17)。
"""

from dataclasses import dataclass

from loreley_crawler.common.clock import Clock
from loreley_crawler.common.errors import is_store_unavailable
from loreley_crawler.common.retry import Retrier
from loreley_crawler.common.timestamps import format_instant
from loreley_crawler.jobs.cancel_requests import CancelRequestRegistry
from loreley_crawler.jobs.job_updates import Applied, apply_job_update
from loreley_crawler.jobs.lock_cleanup import delete_lock_unless_taken_over
from loreley_crawler.jobs.locks import LockStore
from loreley_crawler.jobs.records import JobRecord, JobRecordStore, JobStatus, JobType


@dataclass(frozen=True)
class JobNotFound:
    """そのジョブがない(404 `job_not_found`。ジョブ以外の記録の ID を含む)。"""


@dataclass(frozen=True)
class JobNotCancellable:
    """`source_delete` ジョブ(409 `job_not_cancellable`)。"""


@dataclass(frozen=True)
class JobAlreadyFinished:
    """`crawl` ジョブがすでに終端状態(409 `job_already_finished`。`details.status`)。"""

    status: JobStatus


@dataclass(frozen=True)
class Cancelled:
    """`queued` のジョブを取り消した(200。取り消し完了)。"""

    job_id: str


@dataclass(frozen=True)
class CancelRequested:
    """`running` のジョブへの取り消し要求を受け付けた(202。取り消しは完了していない)。"""

    job_id: str


CancelResult = JobNotFound | JobNotCancellable | JobAlreadyFinished | Cancelled | CancelRequested


class JobCancellation:
    def __init__(
        self,
        *,
        job_store: JobRecordStore,
        lock_store: LockStore,
        cancel_requests: CancelRequestRegistry,
        clock: Clock,
        retrier: Retrier,
    ) -> None:
        self._job_store = job_store
        self._lock_store = lock_store
        self._cancel_requests = cancel_requests
        self._clock = clock
        self._retrier = retrier

    def cancel(self, job_id: str) -> CancelResult:
        job = self._retrier.run(
            lambda: self._job_store.fetch(job_id), is_retryable_error=is_store_unavailable
        )
        if job is None:
            return JobNotFound()
        return self._judge(job)

    def _judge(self, job: JobRecord) -> CancelResult:
        if job.job_type is JobType.SOURCE_DELETE:
            return JobNotCancellable()
        status = job.status
        if status.is_terminal:
            return JobAlreadyFinished(status)
        if status is JobStatus.QUEUED:
            return self._cancel_queued(job)
        return self._request_cancellation(job)

    def _cancel_queued(self, job: JobRecord) -> CancelResult:
        outcome = apply_job_update(
            self._job_store,
            self._retrier,
            job,
            {"status": JobStatus.CANCELLED.value, "finished_at": format_instant(self._clock.now())},
            applicable_statuses=[JobStatus.QUEUED],
        )
        if isinstance(outcome, Applied):
            self._release_lock_of(job)
            return Cancelled(job.job_id)
        # 実行開始(`queued` -> `running`)に負けた。読み直した状態で判定し直す。
        if outcome.current is None:
            return JobNotFound()
        return self._judge(outcome.current)

    def _request_cancellation(self, job: JobRecord) -> CancelResult:
        self._cancel_requests.request(job.job_id)
        # 要求を記録する間に、ジョブが終端になっていた(確認点に達する前に終わった)かもしれない。
        # 終端後に残った要求は誰も消さないので、読み直して、終端なら消して、終了済みとして返す。
        reread = self._retrier.run(
            lambda: self._job_store.fetch(job.job_id), is_retryable_error=is_store_unavailable
        )
        if reread is None:
            self._cancel_requests.clear(job.job_id)
            return JobNotFound()
        if reread.status.is_terminal:
            self._cancel_requests.clear(job.job_id)
            return JobAlreadyFinished(reread.status)
        return CancelRequested(job.job_id)

    def _release_lock_of(self, job: JobRecord) -> None:
        """取り消したジョブのロックを解放する。他のジョブのロックは消さない。"""
        lock = self._retrier.run(
            lambda: self._lock_store.read(job.source_id), is_retryable_error=is_store_unavailable
        )
        if lock is None or lock.job_id != job.job_id:
            return
        self._retrier.run(
            lambda: delete_lock_unless_taken_over(
                self._lock_store, lock, is_target=lambda current: current.job_id == job.job_id
            ),
            is_retryable_error=is_store_unavailable,
        )
