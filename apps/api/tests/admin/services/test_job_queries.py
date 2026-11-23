"""ジョブの一覧・詳細(EP-09・10。C 11章 5・6・16)。

読み取りは偽の Reader(`InMemoryReaders`。検索は古いスナップショット、`mget` はリアルタイム)で、
障害を注入して確かめる。
"""

from datetime import timedelta
from typing import Any

import pytest

from loreley_api.admin.base.codes import (
    DeletionConfirmation,
    DeletionCurrentState,
    JobStatus,
    JobTrigger,
    JobType,
    RegistrationPhase,
    RerunBlockedReason,
    UnavailableReason,
)
from loreley_api.admin.base.errors import AdminApiError
from loreley_api.admin.services.job_queries import JobQueryService
from loreley_api.common.timestamps import format_instant
from tests.admin.factories import make_admin_dependencies
from tests.fakes.clock import DEFAULT_NOW as NOW
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_readers import STORE_TIMEOUT, STORE_UNAVAILABLE, InMemoryReaders
from tests.fakes.inline_runner import InlineRunner

pytestmark = pytest.mark.anyio

STORE = UnavailableReason.STORE_UNAVAILABLE
TIMEOUT = UnavailableReason.TIMEOUT


def at(seconds_from_now: float) -> str:
    return format_instant(NOW + timedelta(seconds=seconds_from_now))


@pytest.fixture
def service(
    readers: InMemoryReaders, fixed_clock: FixedClock, inline_runner: InlineRunner
) -> JobQueryService:
    return make_admin_dependencies(readers, fixed_clock, inline_runner).job_queries


def calls(readers: InMemoryReaders, *operations: str) -> list[str | None]:
    return [call.key for call in readers.behavior.calls_of(*operations)]


async def list_all(service: JobQueryService, **overrides: Any) -> Any:
    arguments: dict[str, Any] = {
        "source_id": None,
        "statuses": (),
        "page": 1,
        "items_per_page": 25,
        "descending": True,
    }
    return await service.list_jobs(**{**arguments, **overrides})


def seed_job(
    readers: InMemoryReaders,
    job_id: str,
    *,
    source_id: str = "docs",
    queued_at: int = 0,
    **fields: Any,
) -> None:
    """`queued_at` は現在からの秒数(大きいほど新しい)。"""
    status = fields.pop("status", "succeeded")
    defaults = {"trigger": "manual", "force_delete": False, "rewrite_mode": False}
    readers.put_job(
        job_id,
        source_id=source_id,
        status=status,
        queued_at=at(queued_at),
        **{**defaults, **fields},
    )


# --- EP-09 ---


async def test_the_list_returns_the_page_with_the_total_and_the_window(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    for number in range(5):
        seed_job(readers, f"job-{number}", queued_at=-number)
    readers.refresh_search()

    response = await list_all(service, items_per_page=2, page=2)

    assert [item.job_id for item in response.items] == ["job-2", "job-3"]
    assert (response.total, response.page, response.items_per_page) == (5, 2, 2)
    assert response.window_limit == 10_000
    assert response.unavailable == {}


async def test_each_row_is_a_job_brief_with_an_empty_unavailable(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_job(
        readers,
        "job-1",
        status="failed",
        started_at=at(-9),
        finished_at=at(-5),
        failure_reason="skip_limit_exceeded",
        rewrite_mode=True,
    )
    readers.refresh_search()

    [item] = (await list_all(service)).items

    assert item.model_dump(mode="json") == {
        "job_id": "job-1",
        "source_id": "docs",
        "job_type": "crawl",
        "trigger": "manual",
        "status": "failed",
        "force_delete": False,
        "rewrite_mode": True,
        "queued_at": at(0),
        "started_at": at(-9),
        "finished_at": at(-5),
        "failure_reason": "skip_limit_exceeded",
        "stalled": False,
        "cancellable": False,
        "unavailable": {},
    }


async def test_the_default_order_is_newest_first_and_ties_are_broken_by_job_id(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_job(readers, "job-b", queued_at=0)
    seed_job(readers, "job-a", queued_at=0)
    seed_job(readers, "job-old", queued_at=-100)
    readers.refresh_search()

    descending = await list_all(service, descending=True)
    ascending = await list_all(service, descending=False)

    assert [item.job_id for item in descending.items] == ["job-a", "job-b", "job-old"]
    assert [item.job_id for item in ascending.items] == ["job-old", "job-a", "job-b"]


async def test_the_list_is_filtered_by_source_and_by_status(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_job(readers, "a-ok", source_id="a", status="succeeded")
    seed_job(readers, "a-failed", source_id="a", status="failed", queued_at=1)
    seed_job(readers, "b-queued", source_id="b", status="queued", queued_at=2)
    seed_job(readers, "b-running", source_id="b", status="running", queued_at=3)
    readers.put_lock("b", job_id="b-running", lease_expires_at=at(60))
    readers.refresh_search()

    by_source = await list_all(service, source_id="a")
    by_status = await list_all(service, statuses=(JobStatus.FAILED,))
    active = await list_all(service, statuses=(JobStatus.QUEUED, JobStatus.RUNNING))

    assert {item.job_id for item in by_source.items} == {"a-ok", "a-failed"}
    assert [item.job_id for item in by_status.items] == ["a-failed"]
    assert {item.job_id for item in active.items} == {"b-queued", "b-running"}
    assert active.total == 2


async def test_an_unregistered_source_gives_an_empty_result_not_an_error(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_job(readers, "job-1")
    readers.refresh_search()

    response = await list_all(service, source_id="no-such-source")

    assert (response.items, response.total, response.unavailable) == ([], 0, {})


async def test_a_list_without_running_jobs_reads_no_locks(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_job(readers, "job-1", status="queued")
    seed_job(readers, "job-2", status="succeeded")
    readers.refresh_search()

    await list_all(service)

    assert calls(readers, "jobs.get_locks", "jobs.get_jobs") == []


async def test_running_rows_are_judged_by_the_lock_and_queued_rows_are_cancellable(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_job(readers, "healthy", source_id="a", status="running", queued_at=4)
    seed_job(readers, "expired", source_id="b", status="running", queued_at=3)
    seed_job(readers, "queued", source_id="c", status="queued", queued_at=2)
    seed_job(readers, "done", source_id="d", status="succeeded", queued_at=1)
    readers.put_lock("a", job_id="healthy", lease_expires_at=at(30))
    readers.put_lock("b", job_id="expired", lease_expires_at=at(-30))
    readers.refresh_search()

    response = await list_all(service)

    states = {item.job_id: (item.stalled, item.cancellable) for item in response.items}
    assert states == {
        "healthy": (False, True),
        "expired": (True, False),
        "queued": (False, True),
        "done": (False, False),
    }
    # ロックは、実行中の行のソースをまとめて 1 回で読む。
    assert calls(readers, "jobs.get_locks") == ["a,b"]


async def test_a_job_that_finished_after_the_search_snapshot_is_shown_as_finished_not_stalled(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    """検索は古い(`running`)が、`mget` はリアルタイム(終了済み・ロックなし)。偽陽性にしない。"""
    seed_job(readers, "job-1", status="running")
    readers.refresh_search()
    readers.update_job("job-1", status="succeeded", finished_at=at(-1))

    [item] = (await list_all(service)).items

    assert item.status is JobStatus.SUCCEEDED
    assert item.finished_at == at(-1)
    assert (item.stalled, item.cancellable) == (False, False)
    assert item.unavailable == {}


async def test_a_running_job_without_a_lock_that_is_still_running_is_stalled(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_job(readers, "job-1", status="running")
    readers.refresh_search()

    [item] = (await list_all(service)).items

    assert (item.status, item.stalled, item.cancellable) == (JobStatus.RUNNING, True, False)


async def test_a_failed_lock_document_marks_only_that_rows_stalled_as_unavailable(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    """EP-09: ロック文書の `mget` の文書単位の失敗は、その行だけ。キーは相対パスの `stalled`。"""
    seed_job(readers, "job-a", source_id="a", status="running", queued_at=3)
    seed_job(readers, "job-b", source_id="b", status="running", queued_at=2)
    seed_job(readers, "job-c", source_id="c", status="queued", queued_at=1)
    readers.put_lock("a", job_id="job-a", lease_expires_at=at(30))
    readers.put_lock("b", job_id="job-b", lease_expires_at=at(30))
    readers.fail_document("jobs.get_locks", "b", STORE_UNAVAILABLE)
    readers.refresh_search()

    response = await list_all(service)

    rows = {item.job_id: item for item in response.items}
    assert (rows["job-a"].stalled, rows["job-a"].unavailable) == (False, {})
    assert (rows["job-b"].stalled, rows["job-b"].cancellable) == (None, False)
    assert rows["job-b"].unavailable == {"stalled": STORE}
    # 実行中でない行は、ロックを読まないので失敗に巻き込まれない(キーなし)。
    assert (rows["job-c"].stalled, rows["job-c"].unavailable) == (False, {})
    # 最上位は行に属さない項目だけで、EP-09 では常に空。
    assert response.unavailable == {}


async def test_a_failed_lock_read_marks_every_running_row_and_prefers_timeout(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_job(readers, "job-a", source_id="a", status="running", queued_at=3)
    seed_job(readers, "job-b", source_id="b", status="running", queued_at=2)
    seed_job(readers, "job-c", source_id="c", status="queued", queued_at=1)
    readers.behavior.inject("jobs.get_locks", STORE_TIMEOUT)
    readers.refresh_search()

    response = await list_all(service)

    rows = {item.job_id: item for item in response.items}
    assert rows["job-a"].unavailable == {"stalled": TIMEOUT}
    assert rows["job-b"].unavailable == {"stalled": TIMEOUT}
    assert rows["job-c"].unavailable == {}
    assert response.unavailable == {}
    # `items[].…` 形式のキーは作らない。
    assert all("[" not in key for item in response.items for key in item.unavailable)


@pytest.mark.parametrize("failed", [STORE_UNAVAILABLE, STORE_TIMEOUT])
async def test_a_failed_list_read_is_a_503_unavailable(
    readers: InMemoryReaders, service: JobQueryService, failed: Any
) -> None:
    seed_job(readers, "job-1")
    readers.refresh_search()
    readers.behavior.inject("jobs.list_jobs", failed)

    with pytest.raises(AdminApiError) as caught:
        await list_all(service)

    assert (caught.value.status_code, caught.value.code, caught.value.retryable) == (
        503,
        "unavailable",
        True,
    )
    # 主たる読み取りが失敗したら、他の読み取りはしない。
    assert calls(readers, "jobs.get_locks", "jobs.get_jobs") == []


async def test_unreadable_stored_values_become_null_and_the_row_is_never_stalled(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    readers.put_job("job-1", source_id="docs", status="mystery", queued_at="garbage", job_type=5)
    readers.refresh_search()

    [item] = (await list_all(service)).items

    assert item.status is None
    assert item.job_type is None
    assert item.queued_at is None
    assert (item.stalled, item.cancellable) == (False, False)
    assert item.unavailable == {}


async def test_the_blocking_reads_go_through_the_runner_in_the_opensearch_category(
    readers: InMemoryReaders, service: JobQueryService, inline_runner: InlineRunner
) -> None:
    seed_job(readers, "job-1", status="running")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(30))
    readers.refresh_search()

    await list_all(service)

    assert inline_runner.categories == ["opensearch", "opensearch"]


# --- EP-10 ---


def seed_detail(readers: InMemoryReaders, job_id: str = "job-1", **fields: Any) -> None:
    status = fields.pop("status", "failed")
    seed_job(
        readers,
        job_id,
        status=status,
        started_at=at(-60),
        finished_at=at(-30),
        failure_reason="skip_limit_exceeded",
        failure_detail="skip_limit_exceeded: 20 consecutive skips",
        **fields,
    )
    readers.put_source("docs", status="active")
    readers.refresh_search()


async def test_a_failed_latest_crawl_of_an_active_source_is_rerunnable(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(
        readers,
        registration={
            "enumerated_count": 1300,
            "created_count": 12,
            "updated_count": 40,
            "unchanged_count": 1100,
            "skipped_count": 20,
            "oversize_count": 1,
            "error_count": 3,
            "invalid_id_count": 0,
            "partial": True,
        },
        settings_snapshot={"ttl": 2_592_000, "ratio_threshold": 0.2, "min_delete_count": 10},
        warnings=[{"code": "invalid_external_id", "count": 2}, "garbage"],
    )

    detail = await service.get_job("job-1")

    assert detail.model_dump(mode="json") == {
        "job_id": "job-1",
        "source_id": "docs",
        "job_type": "crawl",
        "trigger": "manual",
        "status": "failed",
        "force_delete": False,
        "rewrite_mode": False,
        "queued_at": at(0),
        "started_at": at(-60),
        "finished_at": at(-30),
        "failure_reason": "skip_limit_exceeded",
        "stalled": False,
        "cancellable": False,
        "failure_detail": "skip_limit_exceeded: 20 consecutive skips",
        "lease_expires_at": None,
        "latest_for_source": True,
        "rerunnable": True,
        "rerun_blocked_reason": None,
        "cancel_after_finish_notice": False,
        "warnings": [{"code": "invalid_external_id", "count": 2}],
        "registration": {
            "enumerated_count": 1300,
            "created_count": 12,
            "updated_count": 40,
            "unchanged_count": 1100,
            "skipped_count": 20,
            "oversize_count": 1,
            "error_count": 3,
            "invalid_id_count": 0,
            "partial": True,
            "phase": "incomplete",
        },
        "deletion": {
            "summary": None,
            "confirmation": None,
            "current": None,
            "current_state": "not_found",
            "fetched_at": at(0),
            "settings": {
                "ttl_seconds": 2_592_000,
                "ratio_threshold_percent": 20,
                "min_delete_count": 10,
            },
        },
        "unavailable": {},
    }


@pytest.mark.parametrize("job_id", ["no-such-job", "lock-docs", "skip-docs-d1", "maintenance"])
async def test_an_id_that_is_not_a_job_record_is_a_404(
    readers: InMemoryReaders, service: JobQueryService, job_id: str
) -> None:
    """ロック・スキップ記録などの ID を渡されたときも、`record_type` で 404 にする。"""
    readers.put_lock("docs", job_id="job-1")
    readers.put_job("skip-docs-d1", source_id="docs", status="succeeded", record_type="skip")
    readers.put_job("maintenance", source_id="docs", status="succeeded", record_type="maintenance")

    with pytest.raises(AdminApiError) as caught:
        await service.get_job(job_id)

    assert (caught.value.status_code, caught.value.code) == (404, "job_not_found")


async def test_a_failed_job_read_is_a_503_and_never_a_404(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    """読み取りの失敗を、「記録なし」(404)と読み違えない(C 11章 6)。"""
    seed_detail(readers)
    readers.fail_document("jobs.get_jobs", "job-1", STORE_UNAVAILABLE)

    with pytest.raises(AdminApiError) as caught:
        await service.get_job("job-1")

    assert (caught.value.status_code, caught.value.code) == (503, "unavailable")


async def test_a_failed_whole_read_is_a_503(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers)
    readers.behavior.inject("jobs.get_jobs", STORE_TIMEOUT)

    with pytest.raises(AdminApiError) as caught:
        await service.get_job("job-1")

    assert (caught.value.status_code, caught.value.code) == (503, "unavailable")
    # 主たる読み取りが失敗したら、他の読み取りはしない。
    assert calls(readers, "jobs.latest_crawl_id", "sources.get", "deletions.get_result") == []


# `rerunnable` の導出(C 5.3 の表)を、読み取りまで含めて確かめる。


async def rerun_of(service: JobQueryService) -> tuple[bool | None, RerunBlockedReason | None]:
    detail = await service.get_job("job-1")
    return detail.rerunnable, detail.rerun_blocked_reason


async def test_a_source_delete_job_is_not_rerunnable_and_reads_no_crawl_state(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers, job_type="source_delete", status="failed")

    detail = await service.get_job("job-1")

    assert (detail.rerunnable, detail.rerun_blocked_reason) == (False, RerunBlockedReason.NOT_CRAWL)
    assert detail.latest_for_source is False
    assert detail.registration is None
    assert detail.deletion is None
    assert calls(readers, "jobs.latest_crawl_id", "sources.get", "deletions.get_result") == []


async def test_a_job_that_is_not_failed_is_blocked_as_not_failed(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers, status="succeeded")

    assert await rerun_of(service) == (False, RerunBlockedReason.NOT_FAILED)


async def test_a_stalled_running_job_is_blocked_as_stalled_and_shows_the_expired_lease(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers, status="running")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(-5))

    detail = await service.get_job("job-1")

    assert (detail.stalled, detail.cancellable) == (True, False)
    assert detail.lease_expires_at == at(-5)
    assert (detail.rerunnable, detail.rerun_blocked_reason) == (False, RerunBlockedReason.STALLED)


async def test_a_running_job_within_its_lease_is_cancellable_and_not_failed(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers, status="running")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(30))

    detail = await service.get_job("job-1")

    assert (detail.stalled, detail.cancellable, detail.lease_expires_at) == (False, True, at(30))
    assert (detail.rerunnable, detail.rerun_blocked_reason) == (
        False,
        RerunBlockedReason.NOT_FAILED,
    )


async def test_a_job_that_finished_after_the_snapshot_is_shown_as_finished(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    """EP-10 のジョブ記録は `mget`(リアルタイム)なので、検索の遅れの影響を受けない。"""
    seed_detail(readers, status="running")
    readers.update_job("job-1", status="succeeded")
    readers.remove_lock("docs")

    detail = await service.get_job("job-1")

    assert detail.status is JobStatus.SUCCEEDED
    assert (detail.stalled, detail.lease_expires_at) == (False, None)


async def test_a_superseded_failed_crawl_is_blocked_as_superseded(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers)
    seed_job(readers, "job-2", queued_at=100)
    readers.refresh_search()

    detail = await service.get_job("job-1")

    assert detail.latest_for_source is False
    assert (detail.rerunnable, detail.rerun_blocked_reason) == (
        False,
        RerunBlockedReason.SUPERSEDED,
    )


async def test_the_latest_crawl_is_decided_among_the_crawls_of_the_same_source_only(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers)
    seed_job(readers, "other-source-job", source_id="other", queued_at=100)
    seed_job(readers, "delete-job", job_type="source_delete", queued_at=200)
    readers.refresh_search()

    assert (await service.get_job("job-1")).latest_for_source is True


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ({"status": "deleting"}, (False, RerunBlockedReason.SOURCE_DELETING)),
        (None, (False, RerunBlockedReason.SOURCE_MISSING)),
        ({"status": "active"}, (True, None)),
    ],
)
async def test_the_source_settings_decide_the_last_rows_of_the_table(
    readers: InMemoryReaders,
    service: JobQueryService,
    source: dict[str, Any] | None,
    expected: tuple[bool, RerunBlockedReason | None],
) -> None:
    seed_detail(readers)
    readers.remove_source("docs")
    if source is not None:
        readers.put_source("docs", **source)

    assert await rerun_of(service) == expected


async def test_a_failed_source_read_leaves_rerunnable_null_with_the_same_reason(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers)
    readers.behavior.inject("sources.get", STORE_TIMEOUT)

    detail = await service.get_job("job-1")

    assert (detail.rerunnable, detail.rerun_blocked_reason) == (None, None)
    # 他の項目は影響を受けない。
    assert detail.latest_for_source is True
    assert detail.unavailable == {"rerunnable": TIMEOUT}


async def test_a_failed_latest_read_leaves_the_flag_and_rerunnable_null(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers)
    readers.behavior.inject("jobs.latest_crawl_id", STORE_UNAVAILABLE)

    detail = await service.get_job("job-1")

    assert detail.latest_for_source is None
    assert (detail.rerunnable, detail.rerun_blocked_reason) == (None, None)
    assert detail.unavailable == {"latest_for_source": STORE, "rerunnable": STORE}
    assert detail.failure_detail is not None  # 他の項目は読める


async def test_a_failed_lock_read_leaves_stalled_the_lease_and_rerunnable_null(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers, status="running")
    readers.behavior.inject("jobs.get_locks", STORE_TIMEOUT)

    detail = await service.get_job("job-1")

    assert (detail.stalled, detail.cancellable, detail.lease_expires_at) == (None, False, None)
    assert (detail.rerunnable, detail.rerun_blocked_reason) == (None, None)
    assert detail.unavailable == {
        "stalled": TIMEOUT,
        "lease_expires_at": TIMEOUT,
        "rerunnable": TIMEOUT,
    }


async def test_a_failed_lock_read_does_not_hide_a_rerunnable_failed_job(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    """`failed` のジョブは `running` でないのでロックを読まず、ロックの障害の影響を受けない。"""
    seed_detail(readers, status="failed")
    readers.behavior.inject("jobs.get_locks", STORE_UNAVAILABLE, times=None)

    detail = await service.get_job("job-1")

    assert detail.rerunnable is True
    assert detail.unavailable == {}


# `deletion`


async def test_a_queued_crawl_does_not_read_the_deletion_result(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers, status="queued")
    readers.put_deletion_result("job-1", status="completed")

    detail = await service.get_job("job-1")

    assert detail.deletion is not None
    assert detail.deletion.current is None
    assert detail.deletion.current_state is DeletionCurrentState.NOT_FOUND
    assert detail.deletion.fetched_at is None
    assert calls(readers, "deletions.get_result") == []


async def test_the_current_deletion_result_is_available_when_it_exists(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(
        readers,
        deletion_summary={"status": "completed", "target_count": 5, "finished_at": at(-20)},
        confirmation="confirmed",
    )
    readers.put_deletion_result(
        "job-1",
        status="completed",
        reason="ok",
        forced=False,
        target_count=5,
        denominator=100,
        deleted_count=5,
        ended_at=at(-10),
    )

    deletion = (await service.get_job("job-1")).deletion

    assert deletion is not None
    assert deletion.current_state is DeletionCurrentState.AVAILABLE
    assert deletion.fetched_at == at(0)
    assert deletion.confirmation is DeletionConfirmation.CONFIRMED
    assert deletion.current is not None
    assert (deletion.current.status, deletion.current.deleted_count) == ("completed", 5)
    assert deletion.current.ended_at == at(-10)
    assert deletion.summary is not None
    assert (deletion.summary.status, deletion.summary.target_count) == ("completed", 5)
    assert deletion.summary.finished_at == at(-20)


async def test_a_missing_deletion_result_is_not_found_with_the_fetch_time(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers, status="succeeded")

    deletion = (await service.get_job("job-1")).deletion

    assert deletion is not None
    assert (deletion.current, deletion.current_state) == (None, DeletionCurrentState.NOT_FOUND)
    assert deletion.fetched_at == at(0)


async def test_a_failed_deletion_read_is_unavailable_and_not_a_missing_record(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers, status="succeeded")
    readers.put_deletion_result("job-1", status="completed")
    readers.fail_document("deletions.get_result", "job-1", STORE_UNAVAILABLE)

    detail = await service.get_job("job-1")

    assert detail.deletion is not None
    assert (detail.deletion.current, detail.deletion.current_state) == (
        None,
        DeletionCurrentState.UNAVAILABLE,
    )
    assert detail.unavailable == {"deletion.current": STORE}
    # 他の項目は読める。
    assert detail.rerunnable is False


async def test_the_deletion_settings_are_converted_and_unreadable_items_are_null(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(
        readers, settings_snapshot={"ttl": 90, "ratio_threshold": 0.29, "min_delete_count": "x"}
    )

    deletion = (await service.get_job("job-1")).deletion

    assert deletion is not None and deletion.settings is not None
    assert (deletion.settings.ttl_seconds, deletion.settings.ratio_threshold_percent) == (90, 29)
    assert deletion.settings.min_delete_count is None


async def test_a_job_without_a_snapshot_has_no_deletion_settings(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers)

    deletion = (await service.get_job("job-1")).deletion

    assert deletion is not None
    assert deletion.settings is None


# 残りの項目


async def test_cancel_after_finish_notice_needs_a_cancelled_job_with_a_send_start(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers, status="cancelled", finish_notice={"send_started_at": at(-3)})

    detail = await service.get_job("job-1")

    assert detail.cancel_after_finish_notice is True


async def test_the_registration_of_a_queued_job_is_null_and_its_phase_follows_the_status(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers, status="queued")
    seed_detail(readers, "job-2", status="running", registration={"partial": True})
    readers.put_lock("docs", job_id="job-2", lease_expires_at=at(30))

    queued = await service.get_job("job-1")
    running = await service.get_job("job-2")

    assert queued.registration is None
    assert running.registration is not None
    assert running.registration.phase is RegistrationPhase.IN_PROGRESS
    assert (running.trigger, running.job_type) == (JobTrigger.MANUAL, JobType.CRAWL)


async def test_the_failure_detail_is_returned_only_for_a_failed_job(
    readers: InMemoryReaders, service: JobQueryService
) -> None:
    seed_detail(readers, status="cancelled")

    assert (await service.get_job("job-1")).failure_detail is None
