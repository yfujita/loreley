"""ロック文書 → ジョブ記録 → `lock_state`(C 5.1)。読む順序・失敗の扱いを確かめる。"""

import pytest

from loreley_api.admin.base.codes import JobStatus, JobTrigger, JobType, LockState
from loreley_api.admin.derivation.lock_state import ExistingJobView
from loreley_api.admin.services.lock_view import LockViewService
from tests.admin.factories import at
from tests.fakes.clock import DEFAULT_NOW as NOW
from tests.fakes.in_memory_readers import STORE_TIMEOUT, STORE_UNAVAILABLE, InMemoryReaders
from tests.fakes.inline_runner import InlineRunner

pytestmark = pytest.mark.anyio

GRACE_SECONDS = 60.0


@pytest.fixture
def service(readers: InMemoryReaders, inline_runner: InlineRunner) -> LockViewService:
    return LockViewService(
        jobs=readers.jobs,
        runner=inline_runner,  # type: ignore[arg-type]
        grace_seconds=GRACE_SECONDS,
    )


def operations(readers: InMemoryReaders) -> list[str]:
    return [call.operation for call in readers.behavior.calls]


async def test_without_a_lock_document_the_state_is_none_and_no_job_is_read(
    readers: InMemoryReaders, service: LockViewService
) -> None:
    reading = await service.read("docs", now=NOW)

    assert reading.failure is None
    assert reading.lock is not None
    assert reading.lock.state is LockState.NONE
    assert operations(readers) == ["jobs.get_locks"]


async def test_the_lock_is_read_before_the_job_it_names(
    readers: InMemoryReaders, service: LockViewService
) -> None:
    readers.put_job("job-1", source_id="docs", status="running", trigger="schedule")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(30), acquired_at=at(-5))

    reading = await service.read("docs", now=NOW)

    assert reading.lock is not None
    assert reading.lock.state is LockState.HELD_CRAWL
    assert reading.lock.job == ExistingJobView(
        "job-1", JobType.CRAWL, JobStatus.RUNNING, JobTrigger.SCHEDULE, at(30)
    )
    assert reading.lock.acquired_at == at(-5)
    assert operations(readers) == ["jobs.get_locks", "jobs.get_jobs"]
    assert [call.key for call in readers.behavior.calls] == ["docs", "job-1"]


async def test_a_lock_whose_job_record_is_missing_is_decided_by_the_grace_period(
    readers: InMemoryReaders, service: LockViewService
) -> None:
    readers.put_lock("docs", job_id="job-1", acquired_at=at(-10))
    readers.put_lock("old", job_id="job-2", acquired_at=at(-60))

    just_acquired = await service.read("docs", now=NOW)
    orphan = await service.read("old", now=NOW)

    assert just_acquired.lock is not None and just_acquired.lock.state is LockState.JUST_ACQUIRED
    assert orphan.lock is not None and orphan.lock.state is LockState.ORPHAN


async def test_a_lock_without_a_readable_job_id_does_not_read_a_job(
    readers: InMemoryReaders, service: LockViewService
) -> None:
    readers.put_lock("docs", job_id=None, acquired_at=at(-10))

    reading = await service.read("docs", now=NOW)

    assert reading.lock is not None
    assert reading.lock.state is LockState.JUST_ACQUIRED
    assert reading.lock.job is None
    assert operations(readers) == ["jobs.get_locks"]


async def test_the_job_record_that_is_not_a_job_is_treated_as_missing(
    readers: InMemoryReaders, service: LockViewService
) -> None:
    """ロックの `job_id` がロック文書の ID などを指していても、ジョブ記録なしとして扱う。"""
    readers.put_lock("other", job_id="x", acquired_at=at(-3600))
    readers.put_lock("docs", job_id="lock-other", acquired_at=at(-3600))

    reading = await service.read("docs", now=NOW)

    assert reading.lock is not None
    assert reading.lock.state is LockState.ORPHAN


@pytest.mark.parametrize("failed", [STORE_UNAVAILABLE, STORE_TIMEOUT])
async def test_a_failed_lock_read_has_no_lock_and_keeps_the_failure(
    readers: InMemoryReaders, service: LockViewService, failed: object
) -> None:
    readers.put_lock("docs", job_id="job-1")
    readers.behavior.inject("jobs.get_locks", failed)

    reading = await service.read("docs", now=NOW)

    assert reading.lock is None
    assert reading.failure == failed


async def test_a_failed_lock_document_has_no_lock_and_keeps_the_failure(
    readers: InMemoryReaders, service: LockViewService
) -> None:
    readers.put_lock("docs", job_id="job-1")
    readers.fail_document("jobs.get_locks", "docs", STORE_UNAVAILABLE)

    reading = await service.read("docs", now=NOW)

    assert (reading.lock, reading.failure) == (None, STORE_UNAVAILABLE)


async def test_a_failed_job_read_is_unknown_and_keeps_the_job_id_in_the_lock(
    readers: InMemoryReaders, service: LockViewService
) -> None:
    """ジョブ記録の読み取りの失敗を、「記録なし」(`orphan`)と読み違えない。"""
    readers.put_job("job-1", source_id="docs", status="succeeded")
    readers.put_lock("docs", job_id="job-1", acquired_at=at(-3600))
    readers.fail_document("jobs.get_jobs", "job-1", STORE_UNAVAILABLE)

    reading = await service.read("docs", now=NOW)

    assert reading.failure is None
    assert reading.lock is not None
    assert reading.lock.state is LockState.UNKNOWN
    assert reading.lock.job == ExistingJobView("job-1", None, None, None, None)


async def test_the_blocking_reads_go_through_the_runner(
    readers: InMemoryReaders, service: LockViewService, inline_runner: InlineRunner
) -> None:
    readers.put_job("job-1", source_id="docs", status="queued")
    readers.put_lock("docs", job_id="job-1")

    await service.read("docs", now=NOW)

    assert inline_runner.categories == ["opensearch", "opensearch"]
