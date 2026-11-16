"""`scheduler` のテストの共通部品。

メモリ上の Repository(`sources` 用と `jobs` 用は別インスタンス)・本物の受付(`JobAdmission`)・
固定時計で組み立てる。判定は `run_once`(スレッドなし)で確かめ、スレッドのテストは待ちを
`ManualWaiter` で 1 周ずつ進める(スリープに頼らない)。
"""

import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any

from loreley_crawler.jobs import AdmissionResult, JobAdmission, JobStatus, JobType
from loreley_crawler.scheduler import Scheduler, SchedulerSettings, TickWaiter
from loreley_crawler.sources import SourceSettingsInput, SourceStatus
from loreley_crawler.sources.records import build_body
from tests.fakes.clock import DEFAULT_NOW
from tests.jobs.support import NO_WAIT_RETRIER, JobsEnv, fixed_token

# 毎時 0 分。`DEFAULT_NOW`(00:00 UTC)で始めたとき、最初に合う時刻はその 1 時間後。
HOURLY_CRON = "0 * * * *"
FIRST_FIRE_SECONDS = 3_600
SOURCE_ID = "docs"
CHECK_INTERVAL_SECONDS = 30.0


class RecordingAdmission(JobAdmission):
    """定期クロールの受付の呼び出しを、結果つきで記録する。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.scheduled_calls: list[tuple[str, AdmissionResult]] = []
        self.manual_calls = 0
        self.thread_names: list[str] = []

    def accept_scheduled_crawl(self, source_id: str) -> AdmissionResult:
        self.thread_names.append(threading.current_thread().name)
        result = super().accept_scheduled_crawl(source_id)
        self.scheduled_calls.append((source_id, result))
        return result

    def accept_manual_crawl(self, *args: Any, **kwargs: Any) -> AdmissionResult:
        self.manual_calls += 1
        return super().accept_manual_crawl(*args, **kwargs)


def seed_scheduled_source(
    env: JobsEnv,
    source_id: str = SOURCE_ID,
    *,
    cron: str | None = HOURLY_CRON,
    updated_at: datetime = DEFAULT_NOW,
    status: SourceStatus = SourceStatus.ACTIVE,
    connector_config: dict[str, Any] | None = None,
) -> None:
    settings = SourceSettingsInput(
        connector_config=connector_config or {"root": "/data"},
        ttl=2_592_000,
        ratio_threshold=0.3,
        min_delete_count=10,
        schedule_cron=cron,
    )
    body = build_body(source_id, "file_system", settings, status=status, updated_at=updated_at)
    env.sources_repository.seed(source_id, body)


def seed_crawl_job(
    env: JobsEnv,
    number: int,
    queued_at: datetime,
    *,
    source_id: str = SOURCE_ID,
    status: JobStatus = JobStatus.SUCCEEDED,
    job_type: JobType = JobType.CRAWL,
) -> str:
    job_id = f"job-20261113T00{number:02d}00Z-{number:08x}"
    env.seed_job(job_id, source_id=source_id, status=status, job_type=job_type, queued_at=queued_at)
    return job_id


def after(base: datetime, seconds: float) -> datetime:
    return base + timedelta(seconds=seconds)


def make_scheduler(
    env: JobsEnv,
    *,
    waiter: TickWaiter | None = None,
    random_token: Callable[[], str] = fixed_token,
    timezone: tzinfo = UTC,
) -> tuple[Scheduler, RecordingAdmission]:
    admission = RecordingAdmission(
        settings=env.settings,
        source_reader=env.source_reader,
        job_store=env.job_store,
        lock_store=env.lock_store,
        read_maintenance_flag=env.read_maintenance_flag,
        clock=env.clock,
        retrier=NO_WAIT_RETRIER,
        wakeup=env.wakeup,
        random_token=random_token,
    )
    scheduler = Scheduler(
        settings=SchedulerSettings(
            check_interval_seconds=CHECK_INTERVAL_SECONDS, timezone=timezone
        ),
        source_reader=env.source_reader,
        admission=admission,
        clock=env.clock,
        retrier=NO_WAIT_RETRIER,
        waiter=waiter,
    )
    return scheduler, admission
