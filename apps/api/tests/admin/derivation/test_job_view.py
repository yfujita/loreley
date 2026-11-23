"""`JobBrief` の元・`registration`・`warnings`・`failure_detail`(C 5.4)。"""

from typing import Any

import pytest

from loreley_api.admin.base.codes import (
    DocumentExistence,
    JobStatus,
    JobTrigger,
    JobType,
    RegistrationPhase,
)
from loreley_api.admin.derivation.job_view import (
    JobBriefView,
    derive_phase,
    existence_of,
    read_failure_detail,
    read_job_brief,
    read_registration,
    read_warnings,
)

FULL_JOB: dict[str, Any] = {
    "record_type": "job",
    "job_id": "ignored-in-source",
    "source_id": "docs",
    "job_type": "crawl",
    "trigger": "schedule",
    "status": "failed",
    "force_delete": False,
    "rewrite_mode": True,
    "queued_at": "2026-11-22T15:00:00.123Z",
    "started_at": "2026-11-22T15:00:01.020Z",
    "finished_at": "2026-11-22T15:10:04.500Z",
    "failure_reason": "skip_limit_exceeded",
}


def test_a_complete_record_is_read_as_it_is() -> None:
    assert read_job_brief("job-1", FULL_JOB) == JobBriefView(
        job_id="job-1",
        source_id="docs",
        job_type=JobType.CRAWL,
        trigger=JobTrigger.SCHEDULE,
        status=JobStatus.FAILED,
        force_delete=False,
        rewrite_mode=True,
        queued_at="2026-11-22T15:00:00.123Z",
        started_at="2026-11-22T15:00:01.020Z",
        finished_at="2026-11-22T15:10:04.500Z",
        failure_reason="skip_limit_exceeded",
    )


def test_the_job_id_is_the_document_id_not_the_stored_value() -> None:
    assert read_job_brief("document-id", FULL_JOB).job_id == "document-id"


def test_values_that_cannot_be_read_become_none() -> None:
    brief = read_job_brief(
        "job-1",
        {
            "source_id": "docs",
            "job_type": "weird",
            "trigger": 1,
            "status": None,
            "force_delete": "no",
            "rewrite_mode": 0,
            "queued_at": "2026-11-22T15:00:00",
            "started_at": "garbage",
            "finished_at": 5,
        },
    )

    assert brief == JobBriefView(
        "job-1", "docs", None, None, None, None, None, None, None, None, None
    )


def test_an_empty_record_has_only_the_ids() -> None:
    brief = read_job_brief("job-1", {}, fallback_source_id="from-the-request")

    assert (brief.job_id, brief.source_id) == ("job-1", "from-the-request")
    assert brief.status is None


@pytest.mark.parametrize("stored", [None, 1, ""])
def test_the_source_id_falls_back_when_the_stored_value_is_not_a_string(stored: object) -> None:
    brief = read_job_brief("job-1", {"source_id": stored}, fallback_source_id="docs")

    assert brief.source_id == "docs"


def test_the_source_id_is_never_none() -> None:
    assert read_job_brief("job-1", {}).source_id == ""


@pytest.mark.parametrize(
    ("status", "reason", "expected"),
    [
        ("failed", "config_invalid", "config_invalid"),
        # 未知のコードも、解釈せずそのまま返す。
        ("failed", "some_future_code", "some_future_code"),
        ("failed", "", None),
        ("failed", 5, None),
        ("failed", None, None),
        ("cancelled", "config_invalid", None),
        ("running", "config_invalid", None),
        (None, "config_invalid", None),
    ],
)
def test_the_failure_reason_is_returned_only_for_a_failed_job(
    status: object, reason: object, expected: str | None
) -> None:
    brief = read_job_brief("job-1", {"status": status, "failure_reason": reason})

    assert brief.failure_reason == expected


@pytest.mark.parametrize(
    ("status", "detail", "expected"),
    [
        (
            JobStatus.FAILED,
            "skip_limit_exceeded: 20 consecutive skips",
            "skip_limit_exceeded: 20 consecutive skips",
        ),
        (JobStatus.FAILED, 5, None),
        (JobStatus.FAILED, None, None),
        (JobStatus.CANCELLED, "text", None),
        (None, "text", None),
    ],
)
def test_the_failure_detail_is_a_string_of_a_failed_job(
    status: JobStatus | None, detail: object, expected: str | None
) -> None:
    assert read_failure_detail({"failure_detail": detail}, status) == expected


def test_warnings_keep_only_objects_with_a_string_code_as_they_are() -> None:
    warnings = [
        {"code": "invalid_external_id", "count": 3, "examples": ["a", "b"]},
        {"code": 5},
        {"count": 1},
        "text",
        None,
        {"code": "polling_aborted", "confirmation": "unknown"},
    ]

    assert read_warnings({"warnings": warnings}) == [
        {"code": "invalid_external_id", "count": 3, "examples": ["a", "b"]},
        {"code": "polling_aborted", "confirmation": "unknown"},
    ]


@pytest.mark.parametrize("value", [None, "text", {"code": "x"}, 1])
def test_warnings_that_are_not_an_array_are_empty(value: object) -> None:
    assert read_warnings({"warnings": value}) == []
    assert read_warnings({}) == []


REGISTRATION = {
    "enumerated_count": 1300,
    "created_count": 12,
    "updated_count": 40,
    "unchanged_count": 1100,
    "skipped_count": 20,
    "oversize_count": 1,
    "error_count": 3,
    "invalid_id_count": 0,
    "partial": True,
    "unknown_extra": "dropped",
}


def test_the_registration_passes_only_the_documented_items() -> None:
    registration = read_registration(
        {"registration": REGISTRATION}, JobType.CRAWL, JobStatus.FAILED
    )

    assert registration is not None
    assert (registration.enumerated_count, registration.created_count) == (1300, 12)
    assert registration.partial is True
    assert registration.phase is RegistrationPhase.INCOMPLETE
    assert not hasattr(registration, "unknown_extra")


def test_the_registration_is_null_for_a_source_delete_job_and_when_it_is_absent() -> None:
    assert read_registration({"registration": REGISTRATION}, JobType.SOURCE_DELETE, None) is None
    assert read_registration({}, JobType.CRAWL, JobStatus.QUEUED) is None
    assert read_registration({"registration": "text"}, JobType.CRAWL, JobStatus.QUEUED) is None


def test_unreadable_counts_and_partial_are_none_item_by_item() -> None:
    registration = read_registration(
        {"registration": {"enumerated_count": "12", "created_count": True, "partial": "yes"}},
        JobType.CRAWL,
        JobStatus.RUNNING,
    )

    assert registration is not None
    assert registration.enumerated_count is None
    assert registration.created_count is None
    assert registration.updated_count is None
    assert registration.partial is None
    assert registration.phase is None


@pytest.mark.parametrize(
    ("partial", "status", "phase"),
    [
        (False, JobStatus.RUNNING, RegistrationPhase.FINAL),
        (False, JobStatus.SUCCEEDED, RegistrationPhase.FINAL),
        (False, None, RegistrationPhase.FINAL),
        (True, JobStatus.QUEUED, RegistrationPhase.IN_PROGRESS),
        (True, JobStatus.RUNNING, RegistrationPhase.IN_PROGRESS),
        (True, JobStatus.SUCCEEDED, RegistrationPhase.INCOMPLETE),
        (True, JobStatus.PARTIALLY_SUCCEEDED, RegistrationPhase.INCOMPLETE),
        (True, JobStatus.FAILED, RegistrationPhase.INCOMPLETE),
        (True, JobStatus.CANCELLED, RegistrationPhase.INCOMPLETE),
        # `partial` が読めない、または `partial=true` で `status` が読めないときは `null`。
        (None, JobStatus.RUNNING, None),
        (True, None, None),
    ],
)
def test_the_registration_phase_table(
    partial: bool | None, status: JobStatus | None, phase: RegistrationPhase | None
) -> None:
    assert derive_phase(partial, status) is phase


# --- existence(C 5.6) ---


@pytest.mark.parametrize(
    ("document_id", "existing_ids", "expected"),
    [
        ("doc-1", frozenset({"doc-1", "doc-2"}), DocumentExistence.EXISTING),
        ("doc-3", frozenset({"doc-1", "doc-2"}), DocumentExistence.NEW),
        ("doc-1", frozenset(), DocumentExistence.NEW),
        # `document_id` が読めない行は、検索の結果によらず `unknown`。
        (None, frozenset({"doc-1"}), DocumentExistence.UNKNOWN),
        # 一括検索が失敗して分からないときは `unknown`。
        ("doc-1", None, DocumentExistence.UNKNOWN),
        (None, None, DocumentExistence.UNKNOWN),
    ],
)
def test_existence_is_decided_by_the_set_of_ids_found_in_the_search_index(
    document_id: str | None, existing_ids: frozenset[str] | None, expected: DocumentExistence
) -> None:
    assert existence_of(document_id, existing_ids) is expected
