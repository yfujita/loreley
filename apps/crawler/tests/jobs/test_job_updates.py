"""ジョブ記録の版条件つき更新と、競合したときの読み直し(architecture 5.3 の書き手の表)。"""

from typing import Any

import pytest

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.jobs.job_updates import Applied, NotApplicable, apply_job_update
from loreley_crawler.jobs.records import JobStatus
from tests.fakes import in_memory_repository as ops
from tests.fakes.lost_response_repository import LostResponseRepository
from tests.jobs.support import JOB_ID, NO_WAIT_RETRIER, JobsEnv, make_env

RUNNING = [JobStatus.RUNNING]


def bump_job(env: JobsEnv, **fields: Any) -> None:
    env.jobs_repository.seed(JOB_ID, {**env.job_body(JOB_ID), **fields})


def test_an_update_with_the_version_read_is_applied() -> None:
    env = make_env()
    record = env.seed_job(JOB_ID, status=JobStatus.RUNNING)

    outcome = apply_job_update(
        env.job_store, NO_WAIT_RETRIER, record, {"note": "x"}, applicable_statuses=RUNNING
    )

    assert isinstance(outcome, Applied)
    assert env.job_body(JOB_ID)["note"] == "x"
    assert outcome.record.fields["note"] == "x"


def test_a_conflict_is_reread_and_retried_while_the_status_still_applies() -> None:
    env = make_env()
    record = env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    bump_job(env, other="kept")  # 読んだ後に、別の書き込みが入る

    outcome = apply_job_update(
        env.job_store, NO_WAIT_RETRIER, record, {"note": "x"}, applicable_statuses=RUNNING
    )

    assert isinstance(outcome, Applied)
    body = env.job_body(JOB_ID)
    assert (body["note"], body["other"]) == ("x", "kept")


def test_a_conflict_with_a_changed_status_is_reported_without_writing() -> None:
    env = make_env()
    record = env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    bump_job(env, status="failed", failure_reason="lock_released")

    outcome = apply_job_update(
        env.job_store, NO_WAIT_RETRIER, record, {"note": "x"}, applicable_statuses=RUNNING
    )

    assert isinstance(outcome, NotApplicable)
    assert outcome.current is not None
    assert outcome.current.status is JobStatus.FAILED
    assert "note" not in env.job_body(JOB_ID)


def test_a_vanished_record_is_reported_as_not_applicable() -> None:
    env = make_env()
    record = env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    stored = env.jobs_repository.fetch(JOB_ID)
    assert stored is not None
    env.jobs_repository.delete_if_unchanged(
        JOB_ID, seq_no=stored.seq_no, primary_term=stored.primary_term
    )

    outcome = apply_job_update(
        env.job_store, NO_WAIT_RETRIER, record, {"note": "x"}, applicable_statuses=RUNNING
    )

    assert outcome == NotApplicable(None)


def test_a_conflict_that_never_resolves_raises_instead_of_looping() -> None:
    env = make_env()
    record = env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    for _ in range(3):
        env.jobs_repository.behavior.before(ops.REPLACE, lambda: bump_job(env), key=JOB_ID)

    with pytest.raises(StoreUnavailableError) as raised:
        apply_job_update(
            env.job_store, NO_WAIT_RETRIER, record, {"note": "x"}, applicable_statuses=RUNNING
        )

    assert raised.value.reason == "job_update_contention"


def test_a_store_failure_is_retried_and_then_raised() -> None:
    env = make_env()
    record = env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    env.jobs_repository.behavior.inject(
        ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=2
    )

    assert isinstance(
        apply_job_update(
            env.job_store, NO_WAIT_RETRIER, record, {"a": 1}, applicable_statuses=RUNNING
        ),
        Applied,
    )

    env.jobs_repository.behavior.inject(
        ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=None
    )
    current = env.job_store.fetch(JOB_ID)
    assert current is not None
    with pytest.raises(StoreUnavailableError):
        apply_job_update(
            env.job_store, NO_WAIT_RETRIER, current, {"b": 2}, applicable_statuses=RUNNING
        )


def test_a_lost_response_does_not_count_as_a_conflict() -> None:
    repository = LostResponseRepository()
    env = make_env(repository)
    record = env.seed_job(JOB_ID, status=JobStatus.RUNNING)
    repository.lose_response_of(ops.REPLACE)

    outcome = apply_job_update(
        env.job_store, NO_WAIT_RETRIER, record, {"note": "x"}, applicable_statuses=RUNNING
    )

    assert isinstance(outcome, Applied)
    assert env.job_body(JOB_ID)["note"] == "x"
