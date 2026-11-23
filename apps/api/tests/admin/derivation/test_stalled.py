"""`stalled`・`cancellable` の判定(C 5.2)。読み取りの流れは `services/test_stalled_check.py`。"""

from datetime import timedelta
from typing import Any

import pytest

from loreley_api.admin.base.codes import JobStatus, JobType
from loreley_api.admin.derivation.stalled import StalledJudgement, is_cancellable, judge_by_lock
from loreley_api.common.timestamps import format_instant
from tests.fakes.clock import DEFAULT_NOW as NOW


def at(seconds_from_now: float) -> str:
    return format_instant(NOW + timedelta(seconds=seconds_from_now))


def test_a_matching_lock_within_its_lease_is_not_stalled_and_shows_the_lease() -> None:
    lock = {"job_id": "job-1", "lease_expires_at": at(10)}

    assert judge_by_lock(lock, "job-1", NOW) == StalledJudgement(False, at(10))


@pytest.mark.parametrize(("lease_seconds", "stalled"), [(0.001, False), (0, True), (-0.001, True)])
def test_the_lease_boundary_is_expired_at_exactly_now(lease_seconds: float, stalled: bool) -> None:
    lock = {"job_id": "job-1", "lease_expires_at": at(lease_seconds)}

    judgement = judge_by_lock(lock, "job-1", NOW)

    assert judgement is not None
    assert judgement.stalled is stalled


@pytest.mark.parametrize("lease", [None, "garbage", 5, "2026-11-24T00:10:00"])
def test_a_matching_lock_with_a_missing_or_unreadable_lease_is_stalled_without_a_lease(
    lease: Any,
) -> None:
    lock = {"job_id": "job-1", "lease_expires_at": lease}

    assert judge_by_lock(lock, "job-1", NOW) == StalledJudgement(True, None)


@pytest.mark.parametrize(
    "lock",
    [
        None,
        {"job_id": "other-job", "lease_expires_at": "2026-11-24T01:00:00.000Z"},
        {"lease_expires_at": "2026-11-24T01:00:00.000Z"},
        {"job_id": None},
        "not an object",
    ],
)
def test_a_missing_or_foreign_lock_needs_a_confirmation_read(lock: object) -> None:
    assert judge_by_lock(lock, "job-1", NOW) is None


@pytest.mark.parametrize(
    ("job_type", "status", "stalled", "expected"),
    [
        (JobType.CRAWL, JobStatus.QUEUED, False, True),
        # 実行待ちは、`stalled` が決まらなくても取り消せる(ロックを読まない行)。
        (JobType.CRAWL, JobStatus.QUEUED, None, True),
        (JobType.CRAWL, JobStatus.RUNNING, False, True),
        (JobType.CRAWL, JobStatus.RUNNING, True, False),
        # 判定できない(`null`)ときは安全側の `false`。
        (JobType.CRAWL, JobStatus.RUNNING, None, False),
        (JobType.SOURCE_DELETE, JobStatus.QUEUED, False, False),
        (JobType.SOURCE_DELETE, JobStatus.RUNNING, False, False),
        (JobType.CRAWL, JobStatus.SUCCEEDED, False, False),
        (JobType.CRAWL, JobStatus.PARTIALLY_SUCCEEDED, False, False),
        (JobType.CRAWL, JobStatus.FAILED, False, False),
        (JobType.CRAWL, JobStatus.CANCELLED, False, False),
        # 状態・種別が読めないジョブは取り消せない。
        (JobType.CRAWL, None, False, False),
        (None, JobStatus.RUNNING, False, False),
        (None, JobStatus.QUEUED, False, False),
    ],
)
def test_cancellable_table(
    job_type: JobType | None, status: JobStatus | None, stalled: bool | None, expected: bool
) -> None:
    assert is_cancellable(job_type, status, stalled) is expected
