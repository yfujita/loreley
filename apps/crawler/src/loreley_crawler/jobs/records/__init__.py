"""`loreley-jobs` の記録(ジョブ・スキップ・原本サイズ超過・メンテナンスフラグ)の形式と読み書き。

`loreley-jobs` に書くのは `records/` と `locks/` だけ(R7)。
`records/` と `locks/` は互いに依存しない(R6)。
"""

from loreley_crawler.jobs.records.document_records import (
    DocumentRecordStore,
    DocumentRecordType,
    OversizeDetector,
    SkipStage,
    document_record_id,
)
from loreley_crawler.jobs.records.job_ids import generate_job_id
from loreley_crawler.jobs.records.job_record import (
    JOB_RECORD_TYPE,
    FailureReason,
    JobRecord,
    JobStatus,
    JobTrigger,
    JobType,
    new_queued_job_fields,
)
from loreley_crawler.jobs.records.job_store import (
    CreateJobResult,
    JobCreated,
    JobIdCollision,
    JobRecordStore,
    JobSuperseded,
    JobUpdated,
    UpdateJobResult,
)
from loreley_crawler.jobs.records.maintenance_flag import (
    MAINTENANCE_RECORD_ID,
    is_maintenance_enabled,
)
from loreley_crawler.jobs.records.previous_crawl import PreviousCrawl, find_previous_completed_crawl
from loreley_crawler.jobs.records.purge import (
    StoreWriteFailedError,
    delete_document_records_of_source,
    purge_document_records,
)

__all__ = [
    "JOB_RECORD_TYPE",
    "MAINTENANCE_RECORD_ID",
    "CreateJobResult",
    "DocumentRecordStore",
    "DocumentRecordType",
    "FailureReason",
    "JobCreated",
    "JobIdCollision",
    "JobRecord",
    "JobRecordStore",
    "JobStatus",
    "JobSuperseded",
    "JobTrigger",
    "JobType",
    "JobUpdated",
    "OversizeDetector",
    "PreviousCrawl",
    "SkipStage",
    "StoreWriteFailedError",
    "UpdateJobResult",
    "delete_document_records_of_source",
    "document_record_id",
    "find_previous_completed_crawl",
    "generate_job_id",
    "is_maintenance_enabled",
    "new_queued_job_fields",
    "purge_document_records",
]
