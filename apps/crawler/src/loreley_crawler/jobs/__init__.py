"""ジョブの記録・ロックとリース・受付・取り消し・回復・Job Runner(module 4.4)。

`api`・`scheduler`・`crawl`・`source_delete` は、`jobs` の内部(`records/`・`locks/`)ではなく、
ここ(入口)から使う(R3・R4・R6)。入口が公開するもの:
- 受付(`JobAdmission`)・取り消し(`JobCancellation`)・ロック解放(`LockRelease`)と、その型付きの結果
- 起動時の回復(`StartupRecovery`)・Job Runner(`JobRunner`)と、組み立て(`main.py`)が共有する
  `CancelRequestRegistry`・`RunnerWakeup`・設定(`JobsSettings`・`HeartbeatSettings`)、
  周期の待ち(`TickWaiter`・`EventTickWaiter`。`scheduler` も同じ形で使う)
- 実行対象(`crawl`・`source_delete`)が使う `JobExecutor`・`JobContext`・確認点(`Check`)・中断の例外
- ジョブ記録の型(`JobRecord`・`JobStatus`・`JobType`・`JobTrigger`・`FailureReason`)
- 実行対象が使う、記録操作のファサード(`DocumentRecords`・`JobHistory`)と、その引数・結果の型
  (`SkipStage`・`OversizeDetector`・`DocumentRecordType`・`PreviousCrawl`・`StoreWriteFailedError`)。
  `Repository` を内部に束ねる。`crawl`・`source_delete` は R3 により `infrastructure.opensearch`
  を import できないため
"""

from loreley_crawler.jobs.admission import (
    Accepted,
    AcceptedJob,
    AdmissionRejection,
    AdmissionResult,
    JobAdmission,
    LockAlreadyHeld,
    MaintenanceEnabled,
    SourceConfigNotFound,
    SourceDeleting,
)
from loreley_crawler.jobs.cancel_requests import CancelRequestRegistry
from loreley_crawler.jobs.cancellation import (
    Cancelled,
    CancelRequested,
    CancelResult,
    JobAlreadyFinished,
    JobCancellation,
    JobNotCancellable,
    JobNotFound,
)
from loreley_crawler.jobs.context import (
    LOSS_LOCK_NOT_OWNED,
    SETTINGS_SNAPSHOT_KEYS,
    Check,
    JobContext,
)
from loreley_crawler.jobs.existing_job import ExistingJob
from loreley_crawler.jobs.interruptions import (
    CancellationRequested,
    JobInterrupted,
    JobNotStartable,
    MaintenanceDetected,
    OwnershipLost,
)
from loreley_crawler.jobs.lock_release import (
    LockInUse,
    LockRelease,
    LockReleased,
    NoLockToRelease,
    ReleaseLockResult,
)
from loreley_crawler.jobs.locks import EventTickWaiter, HeartbeatSettings, TickWaiter
from loreley_crawler.jobs.log_text import loggable_id
from loreley_crawler.jobs.records import (
    DocumentRecordType,
    FailureReason,
    JobRecord,
    JobStatus,
    JobTrigger,
    JobType,
    OversizeDetector,
    PreviousCrawl,
    SkipStage,
    StoreWriteFailedError,
)
from loreley_crawler.jobs.records_facade import DocumentRecords, JobHistory
from loreley_crawler.jobs.recovery import RecoveryReport, StartupRecovery
from loreley_crawler.jobs.runner import JobExecutor, JobRunner
from loreley_crawler.jobs.settings import OWNER_MAX_BYTES, JobsSettings
from loreley_crawler.jobs.wakeup import RunnerWakeup

__all__ = [
    "LOSS_LOCK_NOT_OWNED",
    "OWNER_MAX_BYTES",
    "SETTINGS_SNAPSHOT_KEYS",
    "Accepted",
    "AcceptedJob",
    "AdmissionRejection",
    "AdmissionResult",
    "CancelRequestRegistry",
    "CancelRequested",
    "CancelResult",
    "CancellationRequested",
    "Cancelled",
    "Check",
    "DocumentRecordType",
    "DocumentRecords",
    "EventTickWaiter",
    "ExistingJob",
    "FailureReason",
    "HeartbeatSettings",
    "JobAdmission",
    "JobAlreadyFinished",
    "JobCancellation",
    "JobContext",
    "JobExecutor",
    "JobHistory",
    "JobInterrupted",
    "JobNotCancellable",
    "JobNotFound",
    "JobNotStartable",
    "JobRecord",
    "JobRunner",
    "JobStatus",
    "JobTrigger",
    "JobType",
    "JobsSettings",
    "LockAlreadyHeld",
    "LockInUse",
    "LockRelease",
    "LockReleased",
    "MaintenanceDetected",
    "MaintenanceEnabled",
    "NoLockToRelease",
    "OversizeDetector",
    "OwnershipLost",
    "PreviousCrawl",
    "RecoveryReport",
    "ReleaseLockResult",
    "RunnerWakeup",
    "SkipStage",
    "SourceConfigNotFound",
    "SourceDeleting",
    "StartupRecovery",
    "StoreWriteFailedError",
    "TickWaiter",
    "loggable_id",
]
