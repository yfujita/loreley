"""`lock_state` の導出(C 5.1 の表。C 11章 5)。猶予の境界は固定時刻で確かめる。"""

from datetime import timedelta
from typing import Any

import pytest

from loreley_api.admin.base.codes import JobStatus, JobTrigger, JobType, LockState
from loreley_api.admin.derivation.lock_state import (
    ExistingJobView,
    JobAbsent,
    JobFound,
    JobLookup,
    JobReadFailed,
    LockDerivation,
    derive_lock,
)
from loreley_api.common.timestamps import format_instant
from tests.fakes.clock import DEFAULT_NOW as NOW

GRACE_SECONDS = 60.0


def at(seconds_from_now: float) -> str:
    return format_instant(NOW + timedelta(seconds=seconds_from_now))


def lock(job_id: Any = "job-1", **fields: Any) -> dict[str, Any]:
    return {
        "record_type": "lock",
        "source_id": "docs",
        "job_id": job_id,
        "acquired_at": at(-3600),
        "lease_expires_at": at(300),
        **fields,
    }


def job(status: Any = "running", job_type: Any = "crawl", **fields: Any) -> JobFound:
    return JobFound({"status": status, "job_type": job_type, "trigger": "manual", **fields})


def state_of(lock_source: object | None, job_lookup: JobLookup | None = None) -> LockState:
    lookup = job_lookup if job_lookup is not None else JobAbsent()
    return derive_lock(lock_source, lookup, now=NOW, grace_seconds=GRACE_SECONDS).state


# 順 2: ロック文書がない。
def test_no_lock_document_is_none() -> None:
    result = derive_lock(None, JobAbsent(), now=NOW, grace_seconds=GRACE_SECONDS)

    assert result == LockDerivation(LockState.NONE, job=None, acquired_at=None)


# 順 3: ロック文書が読めない形(オブジェクトでない)。
@pytest.mark.parametrize("unreadable", ["text", ["a"], 1, True])
def test_a_lock_document_that_is_not_an_object_is_unknown(unreadable: object) -> None:
    result = derive_lock(unreadable, JobAbsent(), now=NOW, grace_seconds=GRACE_SECONDS)

    assert result == LockDerivation(LockState.UNKNOWN, job=None, acquired_at=None)


# 順 4: `job_id` が読め、ジョブ記録の読み取りが失敗。
def test_a_failed_job_read_is_unknown_not_orphan() -> None:
    assert state_of(lock(), JobReadFailed()) == LockState.UNKNOWN


# 順 5: ジョブ記録がない(`job_id` が欠落・文字列でない・空、またはジョブ記録がない)。
@pytest.mark.parametrize(
    ("acquired_seconds_ago", "expected"),
    [
        (0, LockState.JUST_ACQUIRED),
        (59.999, LockState.JUST_ACQUIRED),
        # 猶予の境界は、ちょうど猶予で `orphan`。
        (60, LockState.ORPHAN),
        (60.001, LockState.ORPHAN),
        (3600, LockState.ORPHAN),
    ],
)
@pytest.mark.parametrize(
    "job_id_and_lookup",
    [
        pytest.param(("job-1", JobAbsent()), id="job_record_missing"),
        pytest.param((None, JobAbsent()), id="job_id_null"),
        pytest.param(("", JobAbsent()), id="job_id_empty"),
        pytest.param((123, JobAbsent()), id="job_id_not_a_string"),
    ],
)
def test_without_a_job_record_the_grace_period_splits_just_acquired_from_orphan(
    acquired_seconds_ago: float,
    expected: LockState,
    job_id_and_lookup: tuple[Any, JobLookup],
) -> None:
    job_id, lookup = job_id_and_lookup
    lock_source = lock(job_id, acquired_at=at(-acquired_seconds_ago))

    assert state_of(lock_source, lookup) == expected


def test_a_lock_document_without_job_id_key_follows_the_same_rule() -> None:
    lock_source = lock(acquired_at=at(-10))
    del lock_source["job_id"]

    assert state_of(lock_source) == LockState.JUST_ACQUIRED


@pytest.mark.parametrize("acquired_at", [None, "garbage", 123, "2026-11-23T23:59:59"])
def test_an_unreadable_acquired_at_is_orphan(acquired_at: object) -> None:
    assert state_of(lock(acquired_at=acquired_at)) == LockState.ORPHAN


# 順 6: ジョブの `status` または `job_type` が読めない。
@pytest.mark.parametrize(
    ("status", "job_type"),
    [
        (None, "crawl"),
        ("unexpected", "crawl"),
        (1, "crawl"),
        ("running", None),
        ("running", "maintenance"),
        # 終端でも、種別が読めなければ `unknown`(読めないジョブを `orphan` と言わない)。
        ("failed", "maintenance"),
    ],
)
def test_a_job_with_an_unreadable_status_or_type_is_unknown(
    status: object, job_type: object
) -> None:
    assert state_of(lock(), job(status, job_type)) == LockState.UNKNOWN


# 順 7: 終端のジョブ。
@pytest.mark.parametrize("status", ["succeeded", "partially_succeeded", "failed", "cancelled"])
@pytest.mark.parametrize("job_type", ["crawl", "source_delete"])
def test_a_terminal_job_is_orphan(status: str, job_type: str) -> None:
    assert state_of(lock(), job(status, job_type)) == LockState.ORPHAN


# 順 8: 実行待ち。`lease_expires_at` は見ない。
@pytest.mark.parametrize(
    ("job_type", "expected"),
    [("crawl", LockState.HELD_CRAWL), ("source_delete", LockState.HELD_DELETE)],
)
@pytest.mark.parametrize("lease", [None, "garbage", -100])
def test_a_queued_job_holds_the_lock_whatever_the_lease(
    job_type: str, expected: LockState, lease: object
) -> None:
    lease_expires_at = at(lease) if isinstance(lease, int) else lease

    assert state_of(lock(lease_expires_at=lease_expires_at), job("queued", job_type)) == expected


# 順 9・10: 実行中。
@pytest.mark.parametrize(
    ("job_type", "lease_seconds_from_now", "expected"),
    [
        ("crawl", 0.001, LockState.HELD_CRAWL),
        ("source_delete", 0.001, LockState.HELD_DELETE),
        ("crawl", 3600, LockState.HELD_CRAWL),
        # 期限ちょうどは期限切れ(`now < lease_expires_at` でなければ)。
        ("crawl", 0, LockState.LEASE_EXPIRED),
        ("source_delete", 0, LockState.LEASE_EXPIRED),
        ("crawl", -0.001, LockState.LEASE_EXPIRED),
        ("crawl", -3600, LockState.LEASE_EXPIRED),
    ],
)
def test_a_running_job_holds_the_lock_until_the_lease_expires(
    job_type: str, lease_seconds_from_now: float, expected: LockState
) -> None:
    lock_source = lock(lease_expires_at=at(lease_seconds_from_now))

    assert state_of(lock_source, job("running", job_type)) == expected


@pytest.mark.parametrize(
    "lease", [None, "garbage", 12345, "2026-11-24T00:05:00", "0001-01-01T00:00:00.000Z"]
)
def test_a_running_job_with_a_missing_or_unreadable_lease_is_lease_expired(lease: object) -> None:
    """期限が `null`・読めない値も、過ぎたとみなす。"""
    assert state_of(lock(lease_expires_at=lease), job("running")) == LockState.LEASE_EXPIRED


def test_a_running_job_with_no_lease_key_is_lease_expired() -> None:
    lock_source = lock()
    del lock_source["lease_expires_at"]

    assert state_of(lock_source, job("running")) == LockState.LEASE_EXPIRED


# `lock.job`・`lock.acquired_at`
def test_the_existing_job_is_built_from_the_job_record_and_the_lock_document() -> None:
    lock_source = lock(
        "job-9", acquired_at="2026-11-23T10:00:00.123456+09:00", lease_expires_at=at(60)
    )

    result = derive_lock(
        lock_source,
        job("running", "source_delete", trigger="schedule"),
        now=NOW,
        grace_seconds=GRACE_SECONDS,
    )

    assert result.job == ExistingJobView(
        job_id="job-9",
        job_type=JobType.SOURCE_DELETE,
        status=JobStatus.RUNNING,
        trigger=JobTrigger.SCHEDULE,
        lease_expires_at=at(60),
    )
    assert result.acquired_at == "2026-11-23T01:00:00.123Z"


@pytest.mark.parametrize("lookup", [JobAbsent(), JobReadFailed()])
def test_the_existing_job_has_null_attributes_without_a_readable_job_record(
    lookup: JobLookup,
) -> None:
    result = derive_lock(lock("job-9"), lookup, now=NOW, grace_seconds=GRACE_SECONDS)

    assert result.job == ExistingJobView("job-9", None, None, None, at(300))


def test_unreadable_job_attributes_become_null_in_the_existing_job() -> None:
    result = derive_lock(
        lock("job-9", lease_expires_at="garbage"),
        job("weird", "weird", trigger="weird"),
        now=NOW,
        grace_seconds=GRACE_SECONDS,
    )

    assert result.job == ExistingJobView("job-9", None, None, None, None)


@pytest.mark.parametrize("job_id", [None, "", 5])
def test_the_existing_job_is_null_when_job_id_is_unreadable(job_id: object) -> None:
    result = derive_lock(lock(job_id), JobAbsent(), now=NOW, grace_seconds=GRACE_SECONDS)

    assert result.job is None


def test_acquired_at_is_null_when_unreadable() -> None:
    result = derive_lock(
        lock(acquired_at="garbage"), JobAbsent(), now=NOW, grace_seconds=GRACE_SECONDS
    )

    assert result.acquired_at is None
