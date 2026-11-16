"""`jobs`・`sources` の結果型の全バリアントが、HTTP に写像されていること(取りこぼしがない)。

結果型の `|` の和集合(`AdmissionResult` など)の各メンバーを、写像の関数に渡す。メンバーが増えたとき
(写像の `match` に足し忘れたとき)は、このテストが失敗する。
"""

import json
from datetime import UTC, datetime
from typing import Any, get_args

import pytest

from loreley_crawler.api import responses
from loreley_crawler.jobs import (
    Accepted,
    AcceptedJob,
    AdmissionResult,
    Cancelled,
    CancelRequested,
    CancelResult,
    ExistingJob,
    JobAlreadyFinished,
    JobNotCancellable,
    JobNotFound,
    JobStatus,
    JobTrigger,
    JobType,
    LockAlreadyHeld,
    LockInUse,
    LockReleased,
    MaintenanceEnabled,
    NoLockToRelease,
    ReleaseLockResult,
    SourceConfigNotFound,
    SourceDeleting,
)
from loreley_crawler.sources import (
    AlreadyRegistered,
    Registered,
    RegisterResult,
    RegistrationConflict,
    SourceIsDeleting,
    SourceNotFound,
    SourceRecord,
    SourceStatus,
    Unchanged,
    Updated,
    UpdateResult,
)

NOW = datetime(2026, 11, 13, 1, 2, 3, 456_000, tzinfo=UTC)
EXISTING = ExistingJob("job-1", JobType.CRAWL, JobStatus.RUNNING, JobTrigger.SCHEDULE, NOW)
ACCEPTED = AcceptedJob("job-1", JobType.CRAWL, "docs", JobTrigger.MANUAL, True, False, NOW)
RECORD = SourceRecord(
    "docs", "file_system", {"root": "/data"}, 1, 0.5, 2, None, SourceStatus.ACTIVE, NOW
)


def body_of(response) -> dict[str, Any]:
    return json.loads(response.body)


def error_code(response) -> str:
    return body_of(response)["error"]["code"]


ADMISSION_CASES = [
    (Accepted(ACCEPTED), 202, None),
    (SourceConfigNotFound(), 404, "source_config_not_found"),
    (SourceDeleting(), 409, "source_deleting"),
    (MaintenanceEnabled(), 409, "maintenance_enabled"),
    (LockAlreadyHeld(EXISTING), 409, "lock_held"),
]
CANCEL_CASES = [
    (Cancelled("job-1"), 200, None),
    (CancelRequested("job-1"), 202, None),
    (JobNotFound(), 404, "job_not_found"),
    (JobNotCancellable(), 409, "job_not_cancellable"),
    (JobAlreadyFinished(JobStatus.FAILED), 409, "job_already_finished"),
]
RELEASE_CASES = [
    (LockReleased("job-1"), 200, None),
    (LockReleased(None), 200, None),
    (NoLockToRelease(), 200, None),
    (LockInUse(EXISTING), 409, "lock_in_use"),
]
REGISTER_CASES = [
    (Registered(RECORD), 201, None),
    (AlreadyRegistered(RECORD), 200, None),
    (RegistrationConflict(SourceStatus.ACTIVE), 409, "source_already_exists"),
    (RegistrationConflict(None), 409, "source_already_exists"),
]
UPDATE_CASES = [
    (Updated(RECORD), 200, None),
    (Unchanged(RECORD), 200, None),
    (SourceNotFound(), 404, "source_config_not_found"),
    (SourceIsDeleting(), 409, "source_deleting"),
]


@pytest.mark.parametrize(
    ("union", "cases"),
    [
        (AdmissionResult, ADMISSION_CASES),
        (CancelResult, CANCEL_CASES),
        (ReleaseLockResult, RELEASE_CASES),
        (RegisterResult, REGISTER_CASES),
        (UpdateResult, UPDATE_CASES),
    ],
    ids=["admission", "cancel", "release", "register", "update"],
)
def test_the_cases_cover_every_variant_of_the_result_type(union: Any, cases: list) -> None:
    assert {type(result) for result, _, _ in cases} == set(get_args(union))


@pytest.mark.parametrize(
    ("function", "cases"),
    [
        (responses.admission_response, ADMISSION_CASES),
        (responses.cancel_response, CANCEL_CASES),
        (lambda result: responses.release_lock_response("docs", result), RELEASE_CASES),
        (responses.registration_response, REGISTER_CASES),
        (responses.update_response, UPDATE_CASES),
    ],
    ids=["admission", "cancel", "release", "register", "update"],
)
def test_every_variant_maps_to_its_status_and_error_code(function: Any, cases: list) -> None:
    for result, status_code, code in cases:
        response = function(result)

        assert response.status_code == status_code, result
        if code is None:
            assert "error" not in body_of(response), result
        else:
            assert error_code(response) == code, result


@pytest.mark.parametrize(
    "function",
    [
        responses.admission_response,
        responses.cancel_response,
        lambda result: responses.release_lock_response("docs", result),
        responses.registration_response,
        responses.update_response,
    ],
)
def test_a_result_without_a_mapping_is_an_error_not_a_success(function: Any) -> None:
    with pytest.raises(TypeError, match="no HTTP mapping"):
        function(object())


def test_the_crawl_acceptance_body_carries_the_flags_and_the_source_delete_one_does_not() -> None:
    source_delete = AcceptedJob(
        "job-2", JobType.SOURCE_DELETE, "docs", JobTrigger.MANUAL, False, False, NOW
    )

    crawl = body_of(responses.admission_response(Accepted(ACCEPTED)))
    delete = body_of(responses.admission_response(Accepted(source_delete)))

    assert (crawl["force_delete"], crawl["rewrite_mode"]) == (True, False)
    assert "force_delete" not in delete and "rewrite_mode" not in delete
    assert crawl["queued_at"] == "2026-11-13T01:02:03.456Z"


def test_the_existing_job_body_has_the_five_fields_with_utc_millisecond_time() -> None:
    response = responses.admission_response(LockAlreadyHeld(EXISTING))

    assert body_of(response)["error"]["details"] == {
        "existing_job": {
            "job_id": "job-1",
            "job_type": "crawl",
            "status": "running",
            "trigger": "schedule",
            "lease_expires_at": "2026-11-13T01:02:03.456Z",
        }
    }


def test_the_lock_release_body_distinguishes_released_true_and_false() -> None:
    released = body_of(responses.release_lock_response("docs", LockReleased("job-1")))
    not_released = body_of(responses.release_lock_response("docs", NoLockToRelease()))

    assert released == {"source_id": "docs", "released": True, "failed_job_id": "job-1"}
    assert not_released == {"source_id": "docs", "released": False, "failed_job_id": None}


def test_a_conflict_with_an_unreadable_existing_status_reports_null() -> None:
    response = responses.registration_response(RegistrationConflict(None))

    assert body_of(response)["error"]["details"] == {"status": None}
