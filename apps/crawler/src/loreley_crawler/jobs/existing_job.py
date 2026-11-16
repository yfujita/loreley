"""ロック文書が指す既存のジョブの情報(crawler-api 4.1 の `details.existing_job`)。

受付の拒否(`lock_held`)とロック解放の拒否(`lock_in_use`)が、同じ形で返す。ジョブ記録がない
(孤児ロック)ときは、`job_id` 以外が None。読み取り用の情報なので、形式が不正な項目は例外にせず
None にする(拒否の応答そのものを、不正な記録で失敗させないため)。
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from loreley_crawler.jobs.locks import LockDocument
from loreley_crawler.jobs.records import JobRecord, JobStatus, JobTrigger, JobType


@dataclass(frozen=True)
class ExistingJob:
    job_id: str
    job_type: JobType | None
    status: JobStatus | None
    trigger: JobTrigger | None
    lease_expires_at: datetime | None  # `queued` のジョブのロックは None(architecture 5.1)


def describe_existing_job(lock: LockDocument, job: JobRecord | None) -> ExistingJob:
    fields: dict[str, Any] = dict(job.fields) if job is not None else {}
    return ExistingJob(
        job_id=lock.job_id,
        job_type=_enum_or_none(JobType, fields.get("job_type")),
        status=_enum_or_none(JobStatus, fields.get("status")),
        trigger=_enum_or_none(JobTrigger, fields.get("trigger")),
        lease_expires_at=lock.lease_expires_at,
    )


def _enum_or_none[E: StrEnum](enum_type: type[E], value: object) -> E | None:
    try:
        return enum_type(value)
    except ValueError:
        return None
