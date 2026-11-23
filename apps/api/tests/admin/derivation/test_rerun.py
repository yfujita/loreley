"""`latest_for_source`・`rerunnable`・`rerun_blocked_reason` など、再実行まわりの導出(C 5.3)。"""

from typing import Any

import pytest

from loreley_api.admin.base.codes import JobStatus, JobType, RerunBlockedReason
from loreley_api.admin.derivation.rerun import (
    RerunDecision,
    SourceCondition,
    UndecidedBecause,
    decide_rerun,
    has_cancel_after_finish_notice,
    is_latest_for_source,
    source_condition_of,
)

CRAWL = JobType.CRAWL
FAILED = JobStatus.FAILED
ACTIVE = SourceCondition.ACTIVE


def decide(
    *,
    job_type: JobType | None = CRAWL,
    status: JobStatus | None = FAILED,
    stalled: bool | None = False,
    latest: bool | None = True,
    source: SourceCondition = ACTIVE,
) -> RerunDecision:
    return decide_rerun(
        job_type=job_type, status=status, stalled=stalled, latest_for_source=latest, source=source
    )


def blocked(reason: RerunBlockedReason) -> RerunDecision:
    return RerunDecision(False, reason)


def test_a_failed_latest_crawl_of_an_active_source_is_rerunnable() -> None:
    assert decide() == RerunDecision(True, None)


# 順 1: `crawl` でない(`source_delete` と、読めない `null` を含む)。
@pytest.mark.parametrize("job_type", [JobType.SOURCE_DELETE, None])
def test_a_job_that_is_not_a_crawl_is_blocked_first(job_type: JobType | None) -> None:
    # 他の条件が何であっても、最初に決まる。
    assert decide(job_type=job_type, status=JobStatus.RUNNING, stalled=None) == blocked(
        RerunBlockedReason.NOT_CRAWL
    )


# 順 2・3: 実行中。
def test_a_stalled_running_crawl_is_blocked_as_stalled() -> None:
    assert decide(status=JobStatus.RUNNING, stalled=True) == blocked(RerunBlockedReason.STALLED)


def test_a_running_crawl_whose_stall_is_unknown_is_undecided_because_of_stalled() -> None:
    assert decide(status=JobStatus.RUNNING, stalled=None) == RerunDecision(
        None, None, UndecidedBecause.STALLED
    )


# 順 4: `failed` 以外。
@pytest.mark.parametrize(
    "status",
    [
        JobStatus.QUEUED,
        JobStatus.RUNNING,
        JobStatus.SUCCEEDED,
        JobStatus.PARTIALLY_SUCCEEDED,
        JobStatus.CANCELLED,
        None,
    ],
)
def test_a_status_other_than_failed_is_not_failed(status: JobStatus | None) -> None:
    assert decide(status=status) == blocked(RerunBlockedReason.NOT_FAILED)


# 順 5・6: 最新か。
def test_a_superseded_failed_crawl_is_blocked() -> None:
    assert decide(latest=False) == blocked(RerunBlockedReason.SUPERSEDED)


def test_an_unknown_latest_is_undecided_because_of_latest_for_source() -> None:
    assert decide(latest=None) == RerunDecision(None, None, UndecidedBecause.LATEST_FOR_SOURCE)


# 順 7〜10: データソースの設定。
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (SourceCondition.READ_FAILED, RerunDecision(None, None, UndecidedBecause.SOURCE)),
        (SourceCondition.MISSING, blocked(RerunBlockedReason.SOURCE_MISSING)),
        (SourceCondition.DELETING, blocked(RerunBlockedReason.SOURCE_DELETING)),
        (SourceCondition.ACTIVE, RerunDecision(True, None)),
    ],
)
def test_the_source_condition_decides_last(
    source: SourceCondition, expected: RerunDecision
) -> None:
    assert decide(source=source) == expected


def test_the_evaluation_order_prefers_the_earlier_row() -> None:
    # `superseded`(順 5)は、設定の読み取りの失敗(順 7)より先に決まる。
    assert decide(latest=False, source=SourceCondition.READ_FAILED) == blocked(
        RerunBlockedReason.SUPERSEDED
    )
    # `not_failed`(順 4)は、`latest_for_source` が決まらない(順 6)より先。
    assert decide(status=JobStatus.SUCCEEDED, latest=None) == blocked(RerunBlockedReason.NOT_FAILED)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (None, SourceCondition.MISSING),
        ({"status": "deleting"}, SourceCondition.DELETING),
        ({"status": "active"}, SourceCondition.ACTIVE),
        # `deleting` と読めないものは `active` として扱う。
        ({"status": "weird"}, SourceCondition.ACTIVE),
        ({}, SourceCondition.ACTIVE),
    ],
)
def test_the_source_condition_is_read_from_the_settings_document(
    source: dict[str, Any] | None, expected: SourceCondition
) -> None:
    assert source_condition_of(source) == expected


@pytest.mark.parametrize(
    ("job_type", "latest_crawl_id", "expected"),
    [
        (CRAWL, "job-1", True),
        (CRAWL, "job-2", False),
        (CRAWL, None, False),
        # 種別が `crawl` でないジョブは、ID が一致しても `false`。
        (JobType.SOURCE_DELETE, "job-1", False),
        (None, "job-1", False),
    ],
)
def test_only_the_crawl_that_matches_the_latest_crawl_id_is_the_latest(
    job_type: JobType | None, latest_crawl_id: str | None, expected: bool
) -> None:
    assert is_latest_for_source(job_type, "job-1", latest_crawl_id) is expected


@pytest.mark.parametrize(
    ("status", "job", "expected"),
    [
        (JobStatus.CANCELLED, {"finish_notice": {"send_started_at": "2026-11-24T00:00:00Z"}}, True),
        (JobStatus.CANCELLED, {"finish_notice": {"send_started_at": None}}, False),
        (JobStatus.CANCELLED, {"finish_notice": {"send_started_at": "garbage"}}, False),
        (JobStatus.CANCELLED, {"finish_notice": {}}, False),
        (JobStatus.CANCELLED, {"finish_notice": "text"}, False),
        (JobStatus.CANCELLED, {}, False),
        (JobStatus.FAILED, {"finish_notice": {"send_started_at": "2026-11-24T00:00:00Z"}}, False),
        (None, {"finish_notice": {"send_started_at": "2026-11-24T00:00:00Z"}}, False),
    ],
)
def test_cancel_after_finish_notice_needs_a_cancelled_job_and_a_readable_send_time(
    status: JobStatus | None, job: dict[str, Any], expected: bool
) -> None:
    assert has_cancel_after_finish_notice(status, job) is expected
