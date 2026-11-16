"""`jobs` 直下(受付・取り消し・解放・回復・Job Runner・`JobContext`)のテストの共通部品。

`sources` 用と `jobs` 用の Repository は別のインスタンス(本番も索引ごとに別)。ジョブ記録・
ロック文書・メンテナンスフラグ・ソース設定は、実装を通さず Repository に直接置く(別の書き手による
書き込みの再現にも使う)。スレッドのテストは、スリープに頼らず `Event`・固定時計・ゲートで書き、
待ちには必ず上限を付ける。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loreley_crawler.common.retry import Retrier, RetryPolicy
from loreley_crawler.jobs import (
    CancelRequestRegistry,
    JobsSettings,
    JobStatus,
    JobType,
    RunnerWakeup,
)
from loreley_crawler.jobs.locks import LockDocument, LockStore
from loreley_crawler.jobs.locks.lock_document import new_lock_fields
from loreley_crawler.jobs.records import (
    JobRecord,
    JobRecordStore,
    JobTrigger,
    is_maintenance_enabled,
    new_queued_job_fields,
)
from loreley_crawler.sources import SourceReader, SourceSettingsInput, SourceStatus
from loreley_crawler.sources.records import build_body
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.in_memory_repository import InMemoryRepository

OWNER = "crawler-1"
OTHER_OWNER = "crawler-2"
SOURCE_ID = "docs"
LOCK_ID = f"lock-{SOURCE_ID}"
TOKEN = "0000abcd"
# 固定時計と固定の乱数元で作られる、受付のジョブ ID。
ADMITTED_JOB_ID = f"job-20261113T000000Z-{TOKEN}"
JOB_ID = "job-20261113T000000Z-00000001"
OTHER_JOB_ID = "job-20261113T000000Z-00000002"

# 待ち・合流の上限(不具合で、テストが止まらなくならないように)。
WAIT_TIMEOUT_SECONDS = 5.0

# 待たずに、決定的にリトライする(試行 3 回)。
NO_WAIT_RETRIER = Retrier(
    RetryPolicy(3, 0.0, 1.0, 0.0, 0.0), sleep=lambda _seconds: None, wait_slice_seconds=1_000
)


def fixed_token() -> str:
    return TOKEN


@dataclass
class JobsEnv:
    clock: FixedClock
    jobs_repository: InMemoryRepository
    sources_repository: InMemoryRepository = field(default_factory=InMemoryRepository)
    settings: JobsSettings = field(default_factory=lambda: JobsSettings(owner=OWNER))
    wakeup: RunnerWakeup = field(default_factory=RunnerWakeup)
    cancel_requests: CancelRequestRegistry = field(default_factory=CancelRequestRegistry)

    def __post_init__(self) -> None:
        self.job_store = JobRecordStore(self.jobs_repository)
        self.lock_store = LockStore(self.jobs_repository, self.clock)
        self.source_reader = SourceReader(self.sources_repository)

    def read_maintenance_flag(self) -> bool:
        return is_maintenance_enabled(self.jobs_repository)

    # --- 記録を直接置く・読む ---

    def seed_source(
        self, source_id: str = SOURCE_ID, status: SourceStatus = SourceStatus.ACTIVE
    ) -> None:
        settings = SourceSettingsInput(
            connector_config={"root": "/data"},
            ttl=2_592_000,
            ratio_threshold=0.3,
            min_delete_count=10,
            schedule_cron=None,
        )
        body = build_body(source_id, "file_system", settings, status=status, updated_at=DEFAULT_NOW)
        self.sources_repository.seed(source_id, body)

    def seed_malformed_source(self, source_id: str = SOURCE_ID, **body: Any) -> None:
        self.sources_repository.seed(source_id, {"source_id": source_id, **body})

    def seed_maintenance(self, enabled: object = True) -> None:
        self.jobs_repository.seed("maintenance", {"record_type": "maintenance", "enabled": enabled})

    def seed_job(
        self,
        job_id: str = JOB_ID,
        *,
        status: JobStatus = JobStatus.QUEUED,
        job_type: JobType = JobType.CRAWL,
        source_id: str = SOURCE_ID,
        owner: str = OWNER,
        queued_at: datetime = DEFAULT_NOW,
        **fields: Any,
    ) -> JobRecord:
        body = new_queued_job_fields(
            job_id=job_id,
            job_type=job_type,
            source_id=source_id,
            trigger=JobTrigger.MANUAL,
            owner=owner,
            force_delete=False,
            rewrite_mode=False,
            queued_at=queued_at,
        )
        body.update({"status": status.value, **fields})
        self.jobs_repository.seed(job_id, body)
        record = self.job_store.fetch(job_id)
        assert record is not None
        return record

    def seed_lock(
        self,
        job_id: str = JOB_ID,
        *,
        source_id: str = SOURCE_ID,
        owner: str = OWNER,
        acquired_at: datetime = DEFAULT_NOW,
        **fields: Any,
    ) -> LockDocument:
        body = new_lock_fields(
            source_id=source_id, owner=owner, job_id=job_id, acquired_at=acquired_at
        )
        body.update(fields)
        self.jobs_repository.seed(f"lock-{source_id}", body)
        lock = self.lock_store.read(source_id)
        assert lock is not None
        return lock

    def job_body(self, job_id: str = JOB_ID) -> dict[str, Any]:
        body = self.jobs_repository.body_of(job_id)
        assert body is not None
        return body

    def lock_body(self, source_id: str = SOURCE_ID) -> dict[str, Any] | None:
        return self.jobs_repository.body_of(f"lock-{source_id}")

    def job_ids(self) -> list[str]:
        return [
            record_id
            for record_id in self.jobs_repository.record_ids()
            if record_id.startswith("job-")
        ]


def make_env(jobs_repository: InMemoryRepository | None = None) -> JobsEnv:
    return JobsEnv(FixedClock(), jobs_repository or InMemoryRepository())
