"""ロック解放(crawler-api 4.3)。"""

from datetime import timedelta
from urllib.parse import quote

import pytest

from loreley_crawler.jobs import JobStatus
from tests.api.support import ApiEnv
from tests.fakes.clock import DEFAULT_NOW
from tests.jobs.support import JOB_ID, SOURCE_ID

URL = f"/sources/{SOURCE_ID}/lock"
OLD = DEFAULT_NOW - timedelta(hours=1)
EXPIRED_LEASE = "2026-11-12T23:00:00.000Z"
ACTIVE_LEASE = "2026-11-13T00:05:00.000Z"


def release(api: ApiEnv):
    return api.client.delete(URL)


def test_without_a_lock_it_is_200_released_false_even_if_the_source_config_is_gone(
    api: ApiEnv,
) -> None:
    response = release(api)

    assert response.status_code == 200
    assert response.json() == {"source_id": SOURCE_ID, "released": False, "failed_job_id": None}


def test_an_orphan_lock_is_released_with_200(api: ApiEnv) -> None:
    api.jobs.seed_lock(JOB_ID, acquired_at=OLD)

    response = release(api)

    assert response.status_code == 200
    assert response.json() == {"source_id": SOURCE_ID, "released": True, "failed_job_id": None}
    assert api.jobs.lock_body() is None


def test_the_lock_of_a_finished_job_is_released_without_touching_the_job(api: ApiEnv) -> None:
    api.jobs.seed_job(JOB_ID, status=JobStatus.SUCCEEDED)
    api.jobs.seed_lock(JOB_ID)

    response = release(api)

    assert response.json()["released"] is True
    assert response.json()["failed_job_id"] is None
    assert api.jobs.job_body(JOB_ID)["status"] == "succeeded"


def test_an_expired_running_job_is_failed_and_reported_as_failed_job_id(api: ApiEnv) -> None:
    api.jobs.seed_job(JOB_ID, status=JobStatus.RUNNING)
    api.jobs.seed_lock(JOB_ID, lease_expires_at=EXPIRED_LEASE)

    response = release(api)

    assert response.status_code == 200
    assert response.json() == {"source_id": SOURCE_ID, "released": True, "failed_job_id": JOB_ID}
    job = api.jobs.job_body(JOB_ID)
    assert (job["status"], job["failure_reason"]) == ("failed", "lock_released")


def test_a_running_job_within_its_lease_is_409_lock_in_use_and_nothing_changes(
    api: ApiEnv,
) -> None:
    api.jobs.seed_job(JOB_ID, status=JobStatus.RUNNING)
    api.jobs.seed_lock(JOB_ID, lease_expires_at=ACTIVE_LEASE)

    response = release(api)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "lock_in_use"
    assert error["retryable"] is False
    assert error["details"]["existing_job"] == {
        "job_id": JOB_ID,
        "job_type": "crawl",
        "status": "running",
        "trigger": "manual",
        "lease_expires_at": ACTIVE_LEASE,
    }
    assert api.jobs.lock_body() is not None
    assert api.jobs.job_body(JOB_ID)["status"] == "running"


def test_a_queued_job_is_409_lock_in_use(api: ApiEnv) -> None:
    api.jobs.seed_job(JOB_ID, status=JobStatus.QUEUED)
    api.jobs.seed_lock(JOB_ID)

    response = release(api)

    assert response.status_code == 409
    assert response.json()["error"]["details"]["existing_job"]["status"] == "queued"


def test_a_recent_lock_without_a_job_record_may_be_an_admission_in_progress(api: ApiEnv) -> None:
    api.jobs.seed_lock(JOB_ID, acquired_at=DEFAULT_NOW)

    response = release(api)

    assert response.status_code == 409
    assert response.json()["error"]["details"]["existing_job"] == {
        "job_id": JOB_ID,
        "job_type": None,
        "status": None,
        "trigger": None,
        "lease_expires_at": None,
    }
    assert api.jobs.lock_body() is not None


def test_a_job_record_with_a_malformed_status_is_409_with_a_null_status(api: ApiEnv) -> None:
    api.jobs.seed_job(JOB_ID, status=JobStatus.RUNNING)
    api.jobs.jobs_repository.seed(JOB_ID, {**api.jobs.job_body(JOB_ID), "status": "garbage"})
    api.jobs.seed_lock(JOB_ID, lease_expires_at=EXPIRED_LEASE)

    response = release(api)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "lock_in_use"
    assert response.json()["error"]["details"]["existing_job"]["status"] is None
    assert api.jobs.lock_body() is not None


def test_releasing_twice_is_released_then_not_released(api: ApiEnv) -> None:
    api.jobs.seed_lock(JOB_ID, acquired_at=OLD)

    assert [release(api).json()["released"] for _ in range(2)] == [True, False]


def test_the_maintenance_flag_does_not_stop_a_release(api: ApiEnv) -> None:  # CAPI-P-17
    api.jobs.seed_lock(JOB_ID, acquired_at=OLD)
    api.jobs.seed_maintenance()

    assert release(api).status_code == 200


@pytest.mark.parametrize("source_id", ["-leading", "a b", "x" * 257, "a\nb", "a%b", "é", ".dot"])
def test_a_malformed_source_id_is_400(api: ApiEnv, source_id: str) -> None:
    response = api.client.delete(f"/sources/{quote(source_id, safe='')}/lock")

    assert response.status_code == 400
    assert response.json()["error"]["details"] == {
        "errors": [{"field": "source_id", "reason": "format"}]
    }


def test_a_slash_in_the_source_id_never_reaches_the_handler(api: ApiEnv) -> None:
    api.jobs.seed_lock(JOB_ID, acquired_at=OLD)

    response = api.client.delete("/sources/a%2Fb/lock")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert api.jobs.lock_body() is not None
