"""ジョブ記録の形式(architecture 3.3.1)。

ジョブ記録は `loreley-jobs` の `record_type=job` の記録で、ID は `job_id`。項目の多くは
`running` 以降に `JobContext` が少しずつ足す(`settings_snapshot`・`registration`・
`finish_notice` など)ため、中身は項目の辞書で持ち、よく使う項目だけ型つきで読めるようにする。
`connector_config` はジョブ記録に書かない(`jobs` は Connector の設定の中身を知らない。CM-P-22)。
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from loreley_crawler.common.errors import StoreUnexpectedResponseError
from loreley_crawler.common.timestamps import format_instant

JOB_RECORD_TYPE = "job"


class JobType(StrEnum):
    CRAWL = "crawl"
    SOURCE_DELETE = "source_delete"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIALLY_SUCCEEDED = "partially_succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATUSES


_TERMINAL_STATUSES = frozenset(
    {
        JobStatus.SUCCEEDED,
        JobStatus.PARTIALLY_SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }
)


class FailureReason(StrEnum):
    """`failed` の理由コード(architecture 4.8)。Indexer 側の `reason` とは別の名前空間。"""

    CONFIG_INVALID = "config_invalid"
    ENUMERATION_FAILED = "enumeration_failed"
    INDEXER_UNAVAILABLE = "indexer_unavailable"
    INDEXER_REJECTED = "indexer_rejected"
    EXTERNAL_ID_COLLISION = "external_id_collision"
    ENUMERATION_TOO_LARGE = "enumeration_too_large"
    SKIP_LIMIT_EXCEEDED = "skip_limit_exceeded"
    CONFLICT_UNRESOLVED = "conflict_unresolved"
    LOCK_LOST = "lock_lost"
    DOCUMENT_ID_MISMATCH = "document_id_mismatch"
    MAINTENANCE = "maintenance"
    FINISH_NOTICE_FAILED = "finish_notice_failed"
    INTERNAL_ERROR = "internal_error"
    STORE_UNAVAILABLE = "store_unavailable"
    CRAWLER_RESTART = "crawler_restart"
    LOCK_RELEASED = "lock_released"


class JobTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"


@dataclass(frozen=True)
class JobRecord:
    """読んだ(または書いた)ジョブ記録と、版条件つきの更新に使う版。"""

    job_id: str
    fields: Mapping[str, Any] = field(repr=False)
    seq_no: int
    primary_term: int

    @property
    def status(self) -> JobStatus:
        return self._parse_enum("status", JobStatus)

    @property
    def job_type(self) -> JobType:
        return self._parse_enum("job_type", JobType)

    @property
    def source_id(self) -> str:
        value = self.fields.get("source_id")
        if not isinstance(value, str):
            raise StoreUnexpectedResponseError("malformed_job_record")
        return value

    def _parse_enum[E: StrEnum](self, name: str, enum_type: type[E]) -> E:
        try:
            return enum_type(self.fields.get(name))
        except ValueError:
            # 値は含めない(R11)。
            raise StoreUnexpectedResponseError("malformed_job_record") from None


def new_queued_job_fields(
    *,
    job_id: str,
    job_type: JobType,
    source_id: str,
    trigger: JobTrigger,
    owner: str,
    force_delete: bool,
    rewrite_mode: bool,
    queued_at: datetime,
) -> dict[str, Any]:
    """受付(architecture 4.3 の手順 5)が保存する `queued` のジョブ記録。

    `started_at` 以降の項目は、実行が進んだときに足す。
    """
    return {
        "record_type": JOB_RECORD_TYPE,
        "job_id": job_id,
        "job_type": job_type.value,
        "source_id": source_id,
        "trigger": trigger.value,
        "owner": owner,
        "status": JobStatus.QUEUED.value,
        "queued_at": format_instant(queued_at),
        "force_delete": force_delete,
        "rewrite_mode": rewrite_mode,
    }
