"""`stalled` の確認読み(C 5.2。C 11章 5・6・16)。読む順序と回数は、呼び出しの記録で確かめる。"""

from collections.abc import Callable
from datetime import timedelta

import pytest

from loreley_api.admin.base.codes import JobStatus
from loreley_api.admin.derivation.job_view import JobBriefView, read_job_brief
from loreley_api.admin.services.stalled_check import (
    RunningJob,
    StalledCheck,
    StalledOutcome,
    apply_outcome,
)
from loreley_api.common.results import Failed
from loreley_api.common.timestamps import format_instant
from loreley_api.infrastructure.opensearch import StoredRecord
from loreley_api.infrastructure.opensearch.ports import JOB_BRIEF_FIELDS
from tests.fakes.clock import DEFAULT_NOW as NOW
from tests.fakes.in_memory_readers import STORE_TIMEOUT, STORE_UNAVAILABLE, InMemoryReaders
from tests.fakes.inline_runner import InlineRunner


def at(seconds_from_now: float) -> str:
    return format_instant(NOW + timedelta(seconds=seconds_from_now))


pytestmark = pytest.mark.anyio


@pytest.fixture
def check(readers: InMemoryReaders, inline_runner: InlineRunner) -> StalledCheck:
    return StalledCheck(jobs=readers.jobs, runner=inline_runner)  # type: ignore[arg-type]


def put_running(readers: InMemoryReaders, job_id: str, source_id: str = "docs") -> RunningJob:
    readers.put_job(job_id, source_id=source_id, status="running")
    return RunningJob(job_id, source_id)


async def run_check(check: StalledCheck, *jobs: RunningJob) -> dict[str, StalledOutcome]:
    return await check.check(list(jobs), job_fields=JOB_BRIEF_FIELDS, now=NOW)


def read_operations(readers: InMemoryReaders) -> list[str]:
    return [call.operation for call in readers.behavior.calls]


def on_nth_call(
    readers: InMemoryReaders, operation: str, n: int, action: Callable[[], None]
) -> None:
    """`operation` の n 回目(1 起点)の呼び出しの直前に `action` を実行する。"""
    for _ in range(n - 1):
        readers.behavior.before(operation, lambda: None)
    readers.behavior.before(operation, action)


# --- ロックが一致する(確認読みなし) ---


async def test_a_lock_of_the_job_within_its_lease_is_not_stalled(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    job = put_running(readers, "job-1")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(30))

    outcomes = await run_check(check, job)

    assert outcomes == {"job-1": StalledOutcome(stalled=False, lease_expires_at=at(30))}
    # 確認読みはしない(ロックを 1 回読むだけ)。
    assert read_operations(readers) == ["jobs.get_locks"]


async def test_a_lock_of_the_job_past_its_lease_is_stalled_but_still_shows_the_lease(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    job = put_running(readers, "job-1")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(-1))

    outcomes = await run_check(check, job)

    assert outcomes["job-1"] == StalledOutcome(stalled=True, lease_expires_at=at(-1))
    assert read_operations(readers) == ["jobs.get_locks"]


async def test_a_lock_of_the_job_without_a_readable_lease_is_stalled(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    job = put_running(readers, "job-1")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=None)

    outcomes = await run_check(check, job)

    assert outcomes["job-1"] == StalledOutcome(stalled=True, lease_expires_at=None)


async def test_the_locks_of_all_the_sources_are_read_in_one_call(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    jobs = [put_running(readers, "job-a", "a"), put_running(readers, "job-b", "b")]
    jobs.append(put_running(readers, "job-a2", "a"))
    readers.put_lock("a", job_id="job-a", lease_expires_at=at(30))
    readers.put_lock("b", job_id="job-b", lease_expires_at=at(-30))

    outcomes = await run_check(check, *jobs)

    assert outcomes["job-a"].stalled is False
    assert outcomes["job-b"].stalled is True
    # 同じソースの別のジョブは、そのロックが自分のものでないので確認読みになる。
    assert [call.key for call in readers.behavior.calls_of("jobs.get_locks")] == ["a,b", "a"]


async def test_no_running_job_reads_nothing(readers: InMemoryReaders, check: StalledCheck) -> None:
    assert await run_check(check) == {}
    assert readers.behavior.calls == []


# --- 確認読み(ロックなし・別のジョブのロック) ---


async def test_a_running_job_without_a_lock_is_stalled_after_the_confirmation_reads(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    job = put_running(readers, "job-1")

    outcomes = await run_check(check, job)

    assert outcomes["job-1"].stalled is True
    assert outcomes["job-1"].lease_expires_at is None
    assert outcomes["job-1"].refreshed_job is not None
    # 確認読みは、ロック → ジョブの順(ジョブは `running` → 終端の順にしか変わらないため)。
    assert read_operations(readers) == ["jobs.get_locks", "jobs.get_locks", "jobs.get_jobs"]


async def test_a_lock_of_another_job_is_confirmed_and_the_job_is_stalled(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    job = put_running(readers, "job-1")
    readers.put_lock("docs", job_id="job-2", lease_expires_at=at(300))

    outcomes = await run_check(check, job)

    assert outcomes["job-1"].stalled is True
    assert read_operations(readers) == ["jobs.get_locks", "jobs.get_locks", "jobs.get_jobs"]


async def test_a_job_that_finished_after_it_was_listed_is_not_stalled_and_is_refreshed(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    """一覧(検索。最大約 1 秒古い)で `running` と読んだ後に、ジョブが終わってロックが消えた。

    ロックなしの `running` に見えても、偽陽性にしない(C 11章 16)。
    """
    readers.put_job("job-1", source_id="docs", status="succeeded", finished_at=at(-1))
    listed_as_running = RunningJob("job-1", "docs")

    outcomes = await run_check(check, listed_as_running)

    outcome = outcomes["job-1"]
    assert outcome.stalled is False
    assert outcome.refreshed_job is not None
    assert outcome.refreshed_job.source["status"] == "succeeded"
    assert outcome.refreshed_job.source["finished_at"] == at(-1)


async def test_a_lock_that_appears_by_the_confirmation_decides_by_its_lease(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    job = put_running(readers, "job-1")
    on_nth_call(
        readers,
        "jobs.get_locks",
        2,
        lambda: readers.put_lock("docs", job_id="job-1", lease_expires_at=at(30)),
    )

    outcomes = await run_check(check, job)

    assert outcomes["job-1"].stalled is False
    assert outcomes["job-1"].lease_expires_at == at(30)
    assert outcomes["job-1"].refreshed_job is not None


async def test_a_lock_that_appears_by_the_confirmation_with_an_expired_lease_is_stalled(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    job = put_running(readers, "job-1")
    on_nth_call(
        readers,
        "jobs.get_locks",
        2,
        lambda: readers.put_lock("docs", job_id="job-1", lease_expires_at=at(-30)),
    )

    outcomes = await run_check(check, job)

    assert outcomes["job-1"] == StalledOutcome(
        stalled=True, lease_expires_at=at(-30), refreshed_job=outcomes["job-1"].refreshed_job
    )


async def test_a_job_record_that_vanished_by_the_confirmation_is_not_stalled(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    job = RunningJob("job-1", "docs")  # ジョブ記録は読み直しでは見つからない

    outcomes = await run_check(check, job)

    assert outcomes["job-1"] == StalledOutcome(stalled=False, refreshed_job=None)


async def test_the_confirmation_reads_the_requested_job_fields_only(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    job = put_running(readers, "job-1", "docs")
    readers.update_job("job-1", registration={"partial": True}, failure_detail="x")

    outcomes = await check.check([job], job_fields=("status",), now=NOW)

    refreshed = outcomes["job-1"].refreshed_job
    assert refreshed is not None
    assert refreshed.source == {"status": "running", "record_type": "job"}


# --- 読み取りの失敗 ---


async def test_a_failed_lock_read_makes_every_running_job_undecided_with_the_same_failure(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    jobs = [put_running(readers, "job-a", "a"), put_running(readers, "job-b", "b")]
    readers.behavior.inject("jobs.get_locks", STORE_TIMEOUT)

    outcomes = await run_check(check, *jobs)

    assert outcomes == {
        "job-a": StalledOutcome(stalled=None, failure=STORE_TIMEOUT),
        "job-b": StalledOutcome(stalled=None, failure=STORE_TIMEOUT),
    }
    # 確認読みもしない。
    assert read_operations(readers) == ["jobs.get_locks"]


async def test_a_failed_lock_document_makes_only_that_sources_job_undecided(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    """文書単位の失敗は、その文書のソースの行だけ。他の行は影響を受けない。"""
    jobs = [put_running(readers, "job-a", "a"), put_running(readers, "job-b", "b")]
    readers.put_lock("a", job_id="job-a", lease_expires_at=at(30))
    readers.put_lock("b", job_id="job-b", lease_expires_at=at(30))
    readers.fail_document("jobs.get_locks", "b", STORE_UNAVAILABLE)

    outcomes = await run_check(check, *jobs)

    assert outcomes["job-a"].stalled is False
    assert outcomes["job-b"] == StalledOutcome(stalled=None, failure=STORE_UNAVAILABLE)


async def test_a_failed_job_reread_makes_the_confirmed_job_undecided(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    job = put_running(readers, "job-1")
    readers.behavior.inject("jobs.get_jobs", STORE_UNAVAILABLE)

    outcomes = await run_check(check, job)

    assert outcomes["job-1"] == StalledOutcome(stalled=None, failure=STORE_UNAVAILABLE)


async def test_a_failed_lock_reread_makes_the_confirmed_job_undecided(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    job = put_running(readers, "job-1")
    on_nth_call(
        readers,
        "jobs.get_locks",
        2,
        lambda: readers.fail_document("jobs.get_locks", "docs", STORE_TIMEOUT),
    )

    outcomes = await run_check(check, job)

    assert outcomes["job-1"] == StalledOutcome(stalled=None, failure=STORE_TIMEOUT)


async def test_a_failure_for_one_confirmed_job_does_not_spoil_the_other(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    jobs = [put_running(readers, "job-a", "a"), put_running(readers, "job-b", "b")]
    on_nth_call(
        readers,
        "jobs.get_locks",
        2,
        lambda: readers.fail_document("jobs.get_locks", "b", STORE_UNAVAILABLE),
    )

    outcomes = await run_check(check, *jobs)

    assert outcomes["job-a"].stalled is True
    assert outcomes["job-b"].stalled is None
    assert isinstance(outcomes["job-b"].failure, Failed)


# --- judge: 一覧の行(`JobBriefView`)をまとめて判定する ---


def brief_of(job_id: str, status: str, source_id: str = "docs") -> JobBriefView:
    return read_job_brief(job_id, {"source_id": source_id, "status": status})


async def test_judge_checks_only_the_running_rows_and_keeps_the_order(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    put_running(readers, "job-run", "a")
    readers.put_lock("a", job_id="job-run", lease_expires_at=at(-5))
    briefs = [brief_of("job-done", "succeeded", "b"), brief_of("job-run", "running", "a")]

    judged = await check.judge(briefs, job_fields=JOB_BRIEF_FIELDS, now=NOW)

    assert [(job.brief.job_id, job.stalled, job.failure) for job in judged] == [
        ("job-done", False, None),
        ("job-run", True, None),
    ]
    # 終了済みの行のためには、ロックを読まない。
    assert [call.key for call in readers.behavior.calls_of("jobs.get_locks")] == ["a"]


async def test_judge_without_running_rows_reads_nothing(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    judged = await check.judge([brief_of("job-1", "failed")], job_fields=JOB_BRIEF_FIELDS, now=NOW)

    assert [job.stalled for job in judged] == [False]
    assert readers.behavior.calls == []


async def test_judge_gives_a_failed_row_a_null_stalled_with_its_failure(
    readers: InMemoryReaders, check: StalledCheck
) -> None:
    put_running(readers, "job-1")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(30))
    readers.fail_document("jobs.get_locks", "docs", STORE_TIMEOUT)

    [judged] = await check.judge(
        [brief_of("job-1", "running")], job_fields=JOB_BRIEF_FIELDS, now=NOW
    )

    assert (judged.stalled, judged.failure) == (None, STORE_TIMEOUT)


def test_a_reread_job_replaces_the_row_and_keeps_the_source_id() -> None:
    reread = StoredRecord("job-1", {"status": "succeeded", "finished_at": at(-1)})

    judged = apply_outcome(
        brief_of("job-1", "running"),
        StalledOutcome(stalled=False, refreshed_job=reread),
    )

    assert judged.brief.status is JobStatus.SUCCEEDED
    # 読み直した記録に `source_id` がなくても、行の ID を失わない。
    assert judged.brief.source_id == "docs"
    assert judged.stalled is False


def test_an_outcome_of_none_means_the_job_was_not_running_and_is_not_stalled() -> None:
    judged = apply_outcome(brief_of("job-1", "failed"), None)

    assert (judged.stalled, judged.failure) == (False, None)
