"""クロール起動(crawler-api 4.1)とソース削除ジョブ起動(4.6)。

受付の判断は `jobs` が済ませている。ここでは、結果が HTTP のステータス・コード・本文に写ること、
ボディの検証、判断の順序が `jobs` のまま HTTP に出ることを確かめる。
"""

import threading
from urllib.parse import quote

import pytest

from loreley_crawler.jobs import JobStatus, JobType
from loreley_crawler.sources import SourceStatus
from tests.api.support import SOURCE_ID, ApiEnv
from tests.jobs.support import ADMITTED_JOB_ID, JOB_ID, OTHER_JOB_ID, WAIT_TIMEOUT_SECONDS

CRAWL = f"/sources/{SOURCE_ID}/crawl-jobs"
DELETE = f"/sources/{SOURCE_ID}/delete-jobs"
QUEUED_AT = "2026-11-13T00:00:00.000Z"


def error_of(response) -> dict:
    return response.json()["error"]


# --- クロール起動 ---


def test_a_manual_crawl_is_accepted_with_202_and_the_job_fields(api: ApiEnv) -> None:
    api.jobs.seed_source()

    response = api.post(CRAWL)

    assert response.status_code == 202
    assert response.json() == {
        "job_id": ADMITTED_JOB_ID,
        "job_type": "crawl",
        "source_id": SOURCE_ID,
        "status": "queued",
        "trigger": "manual",
        "force_delete": False,
        "rewrite_mode": False,
        "queued_at": QUEUED_AT,
    }
    job = api.jobs.job_body(ADMITTED_JOB_ID)
    assert (job["job_type"], job["status"], job["trigger"]) == ("crawl", "queued", "manual")
    assert api.jobs.lock_body()["job_id"] == ADMITTED_JOB_ID


@pytest.mark.parametrize("body", [None, {}])
def test_an_empty_body_and_an_empty_object_are_the_same(api: ApiEnv, body: dict | None) -> None:
    api.jobs.seed_source()

    response = api.post(CRAWL, body)

    assert response.status_code == 202
    job = api.jobs.job_body(ADMITTED_JOB_ID)
    assert (job["force_delete"], job["rewrite_mode"]) == (False, False)


def test_force_delete_and_rewrite_mode_are_recorded_on_the_job(api: ApiEnv) -> None:
    api.jobs.seed_source()

    response = api.post(CRAWL, {"force_delete": True, "rewrite_mode": True})

    assert response.status_code == 202
    assert (response.json()["force_delete"], response.json()["rewrite_mode"]) == (True, True)
    job = api.jobs.job_body(ADMITTED_JOB_ID)
    assert (job["force_delete"], job["rewrite_mode"]) == (True, True)


def test_each_flag_is_passed_to_the_job_independently(api: ApiEnv) -> None:
    api.jobs.seed_source()

    response = api.post(CRAWL, {"rewrite_mode": True})

    assert (response.json()["force_delete"], response.json()["rewrite_mode"]) == (False, True)


def test_a_missing_source_is_404_source_config_not_found(api: ApiEnv) -> None:
    response = api.post(CRAWL)

    assert response.status_code == 404
    assert error_of(response)["code"] == "source_config_not_found"
    assert error_of(response)["retryable"] is False
    assert api.jobs.job_ids() == []


def test_a_deleting_source_is_409_source_deleting(api: ApiEnv) -> None:
    api.jobs.seed_source(status=SourceStatus.DELETING)

    response = api.post(CRAWL)

    assert response.status_code == 409
    assert error_of(response)["code"] == "source_deleting"
    assert api.jobs.job_ids() == []


@pytest.mark.parametrize("enabled", [True, "yes", None])
def test_the_maintenance_flag_is_409_maintenance_enabled(api: ApiEnv, enabled: object) -> None:
    api.jobs.seed_source()
    api.jobs.seed_maintenance(enabled)

    response = api.post(CRAWL)

    assert response.status_code == 409
    assert error_of(response)["code"] == "maintenance_enabled"


def test_a_held_lock_is_409_lock_held_with_the_existing_job(api: ApiEnv) -> None:
    api.jobs.seed_source()
    api.jobs.seed_lock(JOB_ID, lease_expires_at="2026-11-13T00:05:00.000Z")
    api.jobs.seed_job(JOB_ID, status=JobStatus.RUNNING, job_type=JobType.SOURCE_DELETE)

    response = api.post(CRAWL)

    assert response.status_code == 409
    error = error_of(response)
    assert error["code"] == "lock_held"
    assert error["details"] == {
        "existing_job": {
            "job_id": JOB_ID,
            "job_type": "source_delete",
            "status": "running",
            "trigger": "manual",
            "lease_expires_at": "2026-11-13T00:05:00.000Z",
        }
    }


def test_a_queued_job_holds_the_lock_without_a_lease(api: ApiEnv) -> None:
    api.jobs.seed_source()
    api.jobs.seed_lock(JOB_ID)
    api.jobs.seed_job(JOB_ID, status=JobStatus.QUEUED)

    existing = error_of(api.post(CRAWL))["details"]["existing_job"]

    assert (existing["status"], existing["lease_expires_at"]) == ("queued", None)


def test_an_orphan_lock_has_null_job_fields_but_its_job_id(api: ApiEnv) -> None:
    api.jobs.seed_source()
    api.jobs.seed_lock(OTHER_JOB_ID)

    existing = error_of(api.post(CRAWL))["details"]["existing_job"]

    assert existing == {
        "job_id": OTHER_JOB_ID,
        "job_type": None,
        "status": None,
        "trigger": None,
        "lease_expires_at": None,
    }


def test_a_job_record_with_a_malformed_status_gives_null_status_not_an_error(api: ApiEnv) -> None:
    api.jobs.seed_source()
    api.jobs.seed_lock(JOB_ID)
    api.jobs.seed_job(JOB_ID, status=JobStatus.RUNNING)
    api.jobs.jobs_repository.seed(JOB_ID, {**api.jobs.job_body(JOB_ID), "status": "garbage"})

    response = api.post(CRAWL)

    assert response.status_code == 409
    assert error_of(response)["details"]["existing_job"]["status"] is None


def test_the_judgement_order_is_source_then_maintenance_then_lock(api: ApiEnv) -> None:
    api.jobs.seed_maintenance()
    api.jobs.seed_lock(JOB_ID)

    assert error_of(api.post(CRAWL))["code"] == "source_config_not_found"

    api.jobs.seed_source()
    assert error_of(api.post(CRAWL))["code"] == "maintenance_enabled"

    api.jobs.seed_maintenance(False)
    assert error_of(api.post(CRAWL))["code"] == "lock_held"


def test_the_second_start_is_rejected_by_the_lock_the_first_one_took(api: ApiEnv) -> None:
    api.jobs.seed_source()

    first = api.post(CRAWL)
    second = api.post(CRAWL)

    assert first.status_code == 202
    assert second.status_code == 409
    assert error_of(second)["details"]["existing_job"]["job_id"] == first.json()["job_id"]


# --- ソース削除ジョブ起動 ---


def test_a_source_delete_is_accepted_without_the_crawl_flags(api: ApiEnv) -> None:
    api.jobs.seed_source()

    response = api.post(DELETE)

    assert response.status_code == 202
    assert response.json() == {
        "job_id": ADMITTED_JOB_ID,
        "job_type": "source_delete",
        "source_id": SOURCE_ID,
        "status": "queued",
        "trigger": "manual",
        "queued_at": QUEUED_AT,
    }


def test_a_source_delete_accepts_a_deleting_source_so_that_it_can_be_rerun(api: ApiEnv) -> None:
    api.jobs.seed_source(status=SourceStatus.DELETING)

    assert api.post(DELETE).status_code == 202


def test_a_source_delete_of_a_missing_source_is_404(api: ApiEnv) -> None:
    response = api.post(DELETE)

    assert response.status_code == 404
    assert error_of(response)["code"] == "source_config_not_found"


def test_a_source_delete_during_maintenance_is_409(api: ApiEnv) -> None:
    api.jobs.seed_source()
    api.jobs.seed_maintenance()

    response = api.post(DELETE)

    assert response.status_code == 409
    assert error_of(response)["code"] == "maintenance_enabled"


def test_a_source_delete_with_a_held_lock_is_409_lock_held(api: ApiEnv) -> None:
    api.jobs.seed_source()
    api.jobs.seed_lock(JOB_ID)
    api.jobs.seed_job(JOB_ID, status=JobStatus.RUNNING, job_type=JobType.SOURCE_DELETE)

    response = api.post(DELETE)

    assert response.status_code == 409
    assert error_of(response)["code"] == "lock_held"


def test_the_delete_endpoint_ignores_a_body(api: ApiEnv) -> None:
    api.jobs.seed_source()

    assert api.post(DELETE, raw=b"not json at all").status_code == 202


def test_two_simultaneous_starts_of_the_same_source_have_exactly_one_winner(api: ApiEnv) -> None:
    api.jobs.seed_source()
    barrier = threading.Barrier(2, timeout=WAIT_TIMEOUT_SECONDS)
    status_codes: list[int] = []

    def start() -> None:
        barrier.wait()
        status_codes.append(api.post(CRAWL).status_code)

    threads = [threading.Thread(target=start) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=WAIT_TIMEOUT_SECONDS)

    assert not any(thread.is_alive() for thread in threads)
    assert sorted(status_codes) == [202, 409]
    assert len(api.jobs.job_ids()) == 1


@pytest.mark.parametrize(
    "source_id", ["-bad", "x" * 257, "a\nb", "a b", "a%b", ".dot", "é"], ids=lambda value: value[:8]
)
@pytest.mark.parametrize("endpoint", ["delete-jobs", "crawl-jobs"])
def test_a_malformed_source_id_is_400_and_creates_no_job_or_lock(
    api: ApiEnv, source_id: str, endpoint: str
) -> None:
    """破壊的なソース削除ジョブ(`delete-jobs`)も、受付の前に `source_id` を検証する。"""
    api.jobs.seed_source(SOURCE_ID)

    response = api.post(f"/sources/{quote(source_id, safe='')}/{endpoint}")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert response.json()["error"]["details"] == {
        "errors": [{"field": "source_id", "reason": "format"}]
    }
    assert api.jobs.job_ids() == []
    assert api.jobs.jobs_repository.record_ids() == []  # ロックも作られない
    assert api.jobs.jobs_repository.write_calls() == []
