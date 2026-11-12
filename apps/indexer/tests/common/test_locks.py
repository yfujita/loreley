from datetime import UTC, datetime, timedelta

from loreley_indexer.common.locks import LockRecord, is_lock_owned

NOW = datetime(2026, 11, 11, 0, 0, 0, tzinfo=UTC)


def lock(
    *, owner: str = "crawler-1", job_id: str = "job-1", expires_in_seconds: float = 60
) -> LockRecord:
    return LockRecord(
        owner=owner, job_id=job_id, lease_expires_at=NOW + timedelta(seconds=expires_in_seconds)
    )


def test_lock_is_owned_when_owner_and_job_match_and_lease_is_valid() -> None:
    assert is_lock_owned(lock(), owner="crawler-1", job_id="job-1", now=NOW)


def test_no_lock_document_is_not_owned() -> None:
    assert not is_lock_owned(None, owner="crawler-1", job_id="job-1", now=NOW)


def test_expired_lease_is_not_owned() -> None:
    assert not is_lock_owned(
        lock(expires_in_seconds=-1), owner="crawler-1", job_id="job-1", now=NOW
    )


def test_lease_expiring_exactly_now_is_not_owned() -> None:
    assert not is_lock_owned(lock(expires_in_seconds=0), owner="crawler-1", job_id="job-1", now=NOW)


def test_different_owner_is_not_owned() -> None:
    assert not is_lock_owned(lock(owner="crawler-2"), owner="crawler-1", job_id="job-1", now=NOW)


def test_different_job_is_not_owned() -> None:
    assert not is_lock_owned(lock(job_id="job-2"), owner="crawler-1", job_id="job-1", now=NOW)
