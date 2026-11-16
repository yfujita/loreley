"""受付: クロール(手動・定期)とソース削除の起動(architecture 4.3 の手順 1〜5。module 4.4・5.1)。

3 つの入口が、同じ手続き `_admit` を共有する。違いは入口の引数で表す。
- `force_delete`・`rewrite_mode` を受け取るのは手動クロールの入口だけ(定期とソース削除は常に false)
- ソース削除は、`status=deleting` のソースも受け付ける(architecture 8.3。再実行で復旧するため)

手順と判定順(crawler-api 4.1): 設定を読む → メンテナンスフラグを読む → ロック文書を `create`
(同時に 2 つの受付が来ても、1 つだけ成功する)→ 設定を読み直す(ソース削除が入っていたらロックを
削除して拒否)→ ジョブ記録(`queued`)を `create`。成功したら Job Runner を起こす。

**巻き戻し**: ロックを取得した後に失敗したら、ロックを版条件つきで削除する(`LockChanged` なら
読み直して判断し直す)。巻き戻しもできないと、ジョブのないロック(孤児ロック)が残る。起動時の
回復(architecture 5.8)か、ロック解放で消す。

Store 層の全体の異常は `Retrier` でリトライし、尽きたら `StoreUnavailableError` を送出する
(api が 503 にする)。HTTP の形は知らない。型付きの結果を返す。
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from loreley_crawler.common.clock import Clock
from loreley_crawler.common.errors import StoreUnavailableError, is_store_unavailable
from loreley_crawler.common.retry import Retrier
from loreley_crawler.jobs.existing_job import ExistingJob, describe_existing_job
from loreley_crawler.jobs.lock_cleanup import delete_lock_unless_taken_over
from loreley_crawler.jobs.locks import LockDocument, LockHeld, LockStore
from loreley_crawler.jobs.log_text import loggable_id
from loreley_crawler.jobs.records import (
    JobCreated,
    JobRecordStore,
    JobStatus,
    JobTrigger,
    JobType,
    new_queued_job_fields,
)
from loreley_crawler.jobs.records.job_ids import RandomToken, generate_job_id, random_hex_token
from loreley_crawler.jobs.settings import JobsSettings
from loreley_crawler.jobs.wakeup import RunnerWakeup
from loreley_crawler.sources import MalformedSourceRecord, SourceReader, SourceRecord, SourceStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AcceptedJob:
    """受け付けた `queued` のジョブ(crawler-api 4.1 の 202 の項目)。"""

    job_id: str
    job_type: JobType
    source_id: str
    trigger: JobTrigger
    force_delete: bool
    rewrite_mode: bool
    queued_at: datetime

    status: JobStatus = JobStatus.QUEUED


@dataclass(frozen=True)
class Accepted:
    job: AcceptedJob


@dataclass(frozen=True)
class SourceConfigNotFound:
    """設定がない(404 `source_config_not_found`)。"""


@dataclass(frozen=True)
class SourceDeleting:
    """ソース削除中のため、新しいクロールを起動しない(409 `source_deleting`)。"""


@dataclass(frozen=True)
class MaintenanceEnabled:
    """メンテナンスフラグが立っている(409 `maintenance_enabled`)。"""


@dataclass(frozen=True)
class LockAlreadyHeld:
    """そのソースのロック文書がすでにある(409 `lock_held`)。

    `existing_job` は、そのロックが指すジョブ。
    """

    existing_job: ExistingJob


AdmissionRejection = SourceConfigNotFound | SourceDeleting | MaintenanceEnabled | LockAlreadyHeld
AdmissionResult = Accepted | AdmissionRejection


@dataclass(frozen=True)
class _Admission:
    """3 つの入口の違い。"""

    source_id: str
    job_type: JobType
    trigger: JobTrigger
    force_delete: bool
    rewrite_mode: bool

    @property
    def accepts_deleting_source(self) -> bool:
        return self.job_type is JobType.SOURCE_DELETE


class JobAdmission:
    def __init__(
        self,
        *,
        settings: JobsSettings,
        source_reader: SourceReader,
        job_store: JobRecordStore,
        lock_store: LockStore,
        read_maintenance_flag: Callable[[], bool],
        clock: Clock,
        retrier: Retrier,
        wakeup: RunnerWakeup,
        random_token: RandomToken = random_hex_token,
    ) -> None:
        self._owner = settings.owner
        self._source_reader = source_reader
        self._job_store = job_store
        self._lock_store = lock_store
        self._read_maintenance_flag = read_maintenance_flag
        self._clock = clock
        self._retrier = retrier
        self._wakeup = wakeup
        self._random_token = random_token

    def accept_manual_crawl(
        self, source_id: str, *, force_delete: bool = False, rewrite_mode: bool = False
    ) -> AdmissionResult:
        return self._admit(
            _Admission(source_id, JobType.CRAWL, JobTrigger.MANUAL, force_delete, rewrite_mode)
        )

    def accept_scheduled_crawl(self, source_id: str) -> AdmissionResult:
        """定期クロール。`force_delete`・`rewrite_mode` は受け取らない(常に false。CA-P-13)。"""
        return self._admit(_Admission(source_id, JobType.CRAWL, JobTrigger.SCHEDULE, False, False))

    def accept_source_delete(self, source_id: str) -> AdmissionResult:
        return self._admit(
            _Admission(source_id, JobType.SOURCE_DELETE, JobTrigger.MANUAL, False, False)
        )

    def _admit(self, admission: _Admission) -> AdmissionResult:
        rejection = self._check_source_and_maintenance(admission)
        if rejection is not None:
            return rejection
        job_id = generate_job_id(self._clock, self._random_token)
        acquired = self._retrier.run(
            lambda: self._lock_store.acquire(
                source_id=admission.source_id, owner=self._owner, job_id=job_id
            ),
            is_retryable_error=is_store_unavailable,
        )
        if isinstance(acquired, LockHeld):
            return LockAlreadyHeld(self._describe_holder(acquired.holder))
        try:
            outcome = self._admit_with_lock(admission, job_id)
        except Exception:
            self._roll_back_after_failure(acquired.lock, admission.source_id)
            raise
        if not isinstance(outcome, Accepted):
            # 設定を読み直したら、ソース削除が入っていた(手順 4)。ロックを削除して拒否する。
            self._roll_back(acquired.lock)
            return outcome
        self._wakeup.notify()
        return outcome

    def _check_source_and_maintenance(self, admission: _Admission) -> AdmissionRejection | None:
        """手順 1・2。"""
        rejection = self._check_source(admission)
        if rejection is not None:
            return rejection
        if self._retrier.run(self._read_maintenance_flag, is_retryable_error=is_store_unavailable):
            return MaintenanceEnabled()
        return None

    def _check_source(self, admission: _Admission) -> SourceConfigNotFound | SourceDeleting | None:
        source = self._retrier.run(
            lambda: self._source_reader.fetch(admission.source_id),
            is_retryable_error=is_store_unavailable,
        )
        if source is None:
            return SourceConfigNotFound()
        if admission.accepts_deleting_source:
            return None
        if _is_deleting(source):
            return SourceDeleting()
        # 値の欠落・型違い(`status` が読めないものを含む)は、受付では検査しない。実行開始の
        # 設定の読み取りが `config_invalid` で `failed` にする(開始通知より前なので害がない)。
        return None

    def _admit_with_lock(self, admission: _Admission, job_id: str) -> Accepted | AdmissionRejection:
        """手順 4・5。ロックを取得した後。失敗(例外)の巻き戻しは、呼び出し側が行う。"""
        rejection = self._check_source(admission)
        if rejection is not None:
            return rejection
        queued_at = self._clock.now()
        fields = new_queued_job_fields(
            job_id=job_id,
            job_type=admission.job_type,
            source_id=admission.source_id,
            trigger=admission.trigger,
            owner=self._owner,
            force_delete=admission.force_delete,
            rewrite_mode=admission.rewrite_mode,
            queued_at=queued_at,
        )
        # 保存する内容は 1 回だけ作る(応答が失われたリトライが、同じ内容の `create` になるように)。
        created = self._retrier.run(
            lambda: self._job_store.create(fields), is_retryable_error=is_store_unavailable
        )
        if not isinstance(created, JobCreated):
            # 同じ `job_id` の別のジョブがある(乱数の衝突。ほぼ起きない)。ロックの `job_id` が
            # この ID なので、ここで作り直さずに巻き戻し、受付を再試行できる異常にする。
            raise StoreUnavailableError("job_id_collision")
        return Accepted(
            AcceptedJob(
                job_id=job_id,
                job_type=admission.job_type,
                source_id=admission.source_id,
                trigger=admission.trigger,
                force_delete=admission.force_delete,
                rewrite_mode=admission.rewrite_mode,
                queued_at=queued_at,
            )
        )

    def _describe_holder(self, holder: LockDocument) -> ExistingJob:
        job = self._retrier.run(
            lambda: self._job_store.fetch(holder.job_id), is_retryable_error=is_store_unavailable
        )
        return describe_existing_job(holder, job)

    def _roll_back(self, lock: LockDocument) -> None:
        """自分のロックを版条件つきで削除する。他のジョブのロックになっていれば消さない。"""
        self._retrier.run(
            lambda: delete_lock_unless_taken_over(
                self._lock_store,
                lock,
                is_target=lambda current: current.is_held_by(lock.owner, lock.job_id),
            ),
            is_retryable_error=is_store_unavailable,
        )

    def _roll_back_after_failure(self, lock: LockDocument, source_id: str) -> None:
        """失敗の巻き戻し。巻き戻しも失敗したら、元の失敗を優先して孤児ロックを残す(警告する)。"""
        try:
            self._roll_back(lock)
        except Exception as error:
            logger.warning(
                "failed to roll back the lock of a failed admission (an orphan lock remains): "
                "source_id=%s error=%s",
                loggable_id(source_id),
                type(error).__name__,
            )


def _is_deleting(source: SourceRecord | MalformedSourceRecord) -> bool:
    return source.status is SourceStatus.DELETING
