"""取り消し(crawler-api 4.2)。"""

from urllib.parse import quote

import pytest

from loreley_crawler.jobs import JobStatus, JobType
from tests.api.support import ApiEnv
from tests.jobs.support import JOB_ID, SOURCE_ID


def cancel(api: ApiEnv, job_id: str = JOB_ID):
    return api.post(f"/jobs/{job_id}/cancel")


def test_a_queued_job_is_cancelled_with_200_and_its_lock_is_released(api: ApiEnv) -> None:
    api.jobs.seed_job(JOB_ID, status=JobStatus.QUEUED)
    api.jobs.seed_lock(JOB_ID)

    response = cancel(api)

    assert response.status_code == 200
    assert response.json() == {"job_id": JOB_ID, "status": "cancelled"}
    assert api.jobs.job_body(JOB_ID)["status"] == "cancelled"
    assert api.jobs.lock_body(SOURCE_ID) is None


def test_a_running_job_gets_202_and_the_request_is_held_in_memory(api: ApiEnv) -> None:
    api.jobs.seed_job(JOB_ID, status=JobStatus.RUNNING)

    response = cancel(api)

    assert response.status_code == 202
    assert response.json() == {"job_id": JOB_ID, "status": "running"}
    assert api.jobs.cancel_requests.is_requested(JOB_ID)
    assert api.jobs.job_body(JOB_ID)["status"] == "running"  # ジョブ記録は書かない


def test_a_repeated_request_to_a_running_job_is_202_again(api: ApiEnv) -> None:
    api.jobs.seed_job(JOB_ID, status=JobStatus.RUNNING)

    assert [cancel(api).status_code for _ in range(3)] == [202, 202, 202]


def test_an_unknown_job_is_404_job_not_found(api: ApiEnv) -> None:
    response = cancel(api, "job-unknown")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "job_not_found"


@pytest.mark.parametrize("record_id", ["lock-docs", "maintenance"])
def test_a_record_that_is_not_a_job_is_404(api: ApiEnv, record_id: str) -> None:
    api.jobs.seed_lock(JOB_ID)
    api.jobs.seed_maintenance()

    assert cancel(api, record_id).status_code == 404


@pytest.mark.parametrize("status", [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.SUCCEEDED])
def test_a_source_delete_job_is_409_job_not_cancellable_in_any_state(
    api: ApiEnv, status: JobStatus
) -> None:
    api.jobs.seed_job(JOB_ID, status=status, job_type=JobType.SOURCE_DELETE)

    response = cancel(api)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "job_not_cancellable"


@pytest.mark.parametrize(
    "status",
    [
        JobStatus.SUCCEEDED,
        JobStatus.PARTIALLY_SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    ],
)
def test_a_finished_crawl_is_409_job_already_finished_with_its_status(
    api: ApiEnv, status: JobStatus
) -> None:
    api.jobs.seed_job(JOB_ID, status=status)

    response = cancel(api)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "job_already_finished"
    assert error["details"] == {"status": status.value}


@pytest.mark.parametrize("job_id", ["a" * 257, "job\nid", "job\x00id", "job\x7fid"])
def test_a_malformed_job_id_is_400_before_any_lookup(api: ApiEnv, job_id: str) -> None:
    response = cancel(api, quote(job_id, safe=""))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert response.json()["error"]["details"] == {
        "errors": [{"field": "job_id", "reason": "format"}]
    }


def test_an_empty_job_id_does_not_match_a_route(api: ApiEnv) -> None:
    response = cancel(api, "")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_a_job_id_of_exactly_256_bytes_is_accepted(api: ApiEnv) -> None:
    assert cancel(api, "a" * 256).status_code == 404  # 検証を通り、ジョブがない


def test_the_job_id_limit_counts_utf8_bytes_not_characters(api: ApiEnv) -> None:
    assert cancel(api, "あ" * 86).status_code == 400  # 258 バイト
    assert cancel(api, "あ" * 85).status_code == 404  # 255 バイト


def test_the_maintenance_flag_does_not_stop_a_cancellation(api: ApiEnv) -> None:  # CAPI-P-17
    api.jobs.seed_job(JOB_ID, status=JobStatus.RUNNING)
    api.jobs.seed_maintenance()

    assert cancel(api).status_code == 202
