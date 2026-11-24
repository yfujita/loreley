"""データソースの一覧・詳細(EP-01・02。C 11章 5・6・16)。

読み取りは偽の Reader(`InMemoryReaders`。検索は古いスナップショット、`mget` はリアルタイム)で、
障害を注入して確かめる。EP-01 は、**行ごとの成否の区別**(C 11章 6)が中心。
"""

from typing import Any

import pytest

from loreley_api.admin.base.codes import JobStatus, JobTrigger, LockState, SourceStatus
from loreley_api.admin.base.errors import AdminApiError
from loreley_api.admin.schemas.sources import SourceListItem
from loreley_api.admin.services.source_catalog import SourceCatalogService
from loreley_api.common.results import Failed
from tests.admin.factories import at, make_admin_dependencies, seed_job
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_readers import (
    SEARCH_TIMEOUT,
    SEARCH_UNAVAILABLE,
    STORE_TIMEOUT,
    STORE_UNAVAILABLE,
    InMemoryReaders,
)
from tests.fakes.inline_runner import InlineRunner

pytestmark = pytest.mark.anyio


@pytest.fixture
def service(
    readers: InMemoryReaders, fixed_clock: FixedClock, inline_runner: InlineRunner
) -> SourceCatalogService:
    return make_admin_dependencies(readers, fixed_clock, inline_runner).source_catalog


def seed_source(readers: InMemoryReaders, source_id: str, **fields: Any) -> None:
    defaults: dict[str, Any] = {
        "connector_type": "file_system",
        "connector_config": {"root": "/data/documents"},
        "ttl": 2_592_000,
        "ratio_threshold": 0.2,
        "min_delete_count": 10,
        "schedule_cron": None,
        "status": "active",
        "updated_at": at(-3600),
    }
    readers.put_source(source_id, **{**defaults, **fields})


def seed_documents(readers: InMemoryReaders, source_id: str, count: int) -> None:
    for number in range(count):
        readers.put_document(
            f"{source_id}-doc-{number}", source_id=source_id, index_status="indexed"
        )


async def list_items(service: SourceCatalogService) -> dict[str, SourceListItem]:
    response = await service.list_sources()
    return {item.source_id: item for item in response.items}


def operations(readers: InMemoryReaders) -> list[str]:
    return [call.operation for call in readers.behavior.calls]


# --- EP-01: 形 ---


async def test_a_row_has_the_source_the_latest_jobs_and_the_document_count(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs", schedule_cron="0 3 * * *")
    seed_job(
        readers,
        "job-old",
        "docs",
        status="succeeded",
        queued_at=-200,
        finished_at=at(-190),
    )
    seed_job(
        readers,
        "job-new",
        "docs",
        status="failed",
        queued_at=-100,
        started_at=at(-99),
        finished_at=at(-90),
        failure_reason="enumeration_failed",
    )
    seed_documents(readers, "docs", 3)
    readers.refresh_search()

    response = await service.list_sources()

    [item] = response.items
    assert item.model_dump(mode="json") == {
        "source_id": "docs",
        "connector_type": "file_system",
        "schedule_cron": "0 3 * * *",
        "status": "active",
        "last_crawl": {
            "job_id": "job-new",
            "source_id": "docs",
            "job_type": "crawl",
            "trigger": "manual",
            "status": "failed",
            "force_delete": False,
            "rewrite_mode": False,
            "queued_at": at(-100),
            "started_at": at(-99),
            "finished_at": at(-90),
            "failure_reason": "enumeration_failed",
            "stalled": False,
            "cancellable": False,
        },
        "last_completed_at": at(-190),
        "delete_job": None,
        "document_count": 3,
        "unavailable": {},
    }
    assert response.unavailable == {}


async def test_rows_are_in_source_id_order_and_an_empty_catalog_reads_nothing_else(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    assert (await service.list_sources()).items == []
    assert operations(readers) == ["sources.list_all"]

    for source_id in ("zeta", "alpha", "mid"):
        seed_source(readers, source_id)
    readers.refresh_search()

    response = await service.list_sources()

    assert [item.source_id for item in response.items] == ["alpha", "mid", "zeta"]


async def test_a_source_that_never_ran_has_null_jobs_and_a_zero_count_without_any_key(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs")
    readers.refresh_search()

    [item] = (await service.list_sources()).items

    assert item.last_crawl is None
    assert item.last_completed_at is None
    assert item.delete_job is None
    assert item.document_count == 0
    assert item.unavailable == {}


async def test_the_last_completed_at_ignores_failed_and_cancelled_jobs(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs")
    seed_job(readers, "ok-1", "docs", status="succeeded", queued_at=-50, finished_at=at(-40))
    seed_job(
        readers, "ok-2", "docs", status="partially_succeeded", queued_at=-30, finished_at=at(-20)
    )
    seed_job(readers, "bad", "docs", status="failed", queued_at=-10, finished_at=at(-5))
    seed_job(readers, "stop", "docs", status="cancelled", queued_at=-2, finished_at=at(-1))
    readers.refresh_search()

    [item] = (await service.list_sources()).items

    assert item.last_completed_at == at(-20)
    assert item.last_crawl is not None
    assert item.last_crawl.job_id == "stop"


async def test_the_delete_job_is_shown_only_for_a_source_that_is_being_deleted(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "active-source")
    seed_job(readers, "old-delete", "active-source", job_type="source_delete", queued_at=-5)
    seed_source(readers, "deleting-source", status="deleting")
    seed_job(
        readers,
        "delete-1",
        "deleting-source",
        job_type="source_delete",
        status="queued",
        queued_at=-3,
    )
    readers.refresh_search()

    items = await list_items(service)

    assert items["active-source"].delete_job is None
    assert items["active-source"].status is SourceStatus.ACTIVE
    delete_job = items["deleting-source"].delete_job
    assert delete_job is not None
    assert (delete_job.job_id, delete_job.status, delete_job.cancellable) == (
        "delete-1",
        JobStatus.QUEUED,
        False,  # `source_delete` は取り消せない
    )


async def test_unreadable_source_values_are_null_without_a_key(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    readers.put_source("docs", connector_type=5, schedule_cron=7, status="paused")
    readers.refresh_search()

    [item] = (await service.list_sources()).items

    assert (item.connector_type, item.schedule_cron, item.status) == (None, None, None)
    assert item.unavailable == {}


# --- EP-01: 主たる読み取りの失敗 ---


@pytest.mark.parametrize("failed", [STORE_UNAVAILABLE, STORE_TIMEOUT])
async def test_a_failed_source_list_is_a_503_and_nothing_else_is_read(
    readers: InMemoryReaders, service: SourceCatalogService, failed: Failed
) -> None:
    seed_source(readers, "docs")
    readers.refresh_search()
    readers.behavior.inject("sources.list_all", failed)

    with pytest.raises(AdminApiError) as raised:
        await service.list_sources()

    assert (raised.value.status_code, raised.value.code) == (503, "unavailable")
    assert operations(readers) == ["sources.list_all"]


# --- EP-01: 行ごとの成否の区別(C 11章 6) ---


async def test_a_never_run_row_and_a_failed_lock_row_are_told_apart(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    """B 2.2 の例: source-a は未実行で値がない(キーなし)、source-b はロックの読み取りが失敗。"""
    seed_source(readers, "source-a")
    seed_source(readers, "source-b")
    seed_job(readers, "job-b", "source-b", status="running", started_at=at(-10))
    readers.put_lock("source-b", job_id="job-b", lease_expires_at=at(60))
    readers.fail_document("jobs.get_locks", "source-b", STORE_UNAVAILABLE)
    readers.refresh_search()

    response = await service.list_sources()

    items = {item.source_id: item for item in response.items}
    source_a, source_b = items["source-a"], items["source-b"]
    # 2 行とも `last_crawl` の値は読めていないが、キーの有無で区別できる。
    assert source_a.last_crawl is None
    assert source_a.unavailable == {}
    assert source_b.last_crawl is not None
    assert source_b.last_crawl.stalled is None
    assert source_b.last_crawl.cancellable is False
    assert source_b.unavailable == {"last_crawl.stalled": "store_unavailable"}
    assert response.unavailable == {}


async def test_a_failed_lock_document_affects_only_the_row_of_that_source(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    for source_id in ("a", "b", "c"):
        seed_source(readers, source_id)
        seed_job(readers, f"job-{source_id}", source_id, status="running")
        readers.put_lock(source_id, job_id=f"job-{source_id}", lease_expires_at=at(60))
    readers.fail_document("jobs.get_locks", "b", STORE_TIMEOUT)
    readers.refresh_search()

    items = await list_items(service)

    assert [(items[s].last_crawl.stalled, items[s].unavailable) for s in "ac"] == [  # type: ignore[union-attr]
        (False, {}),
        (False, {}),
    ]
    assert items["b"].last_crawl.stalled is None  # type: ignore[union-attr]
    assert items["b"].unavailable == {"last_crawl.stalled": "timeout"}


async def test_the_locks_of_all_running_rows_are_read_in_one_call(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    for source_id in ("a", "b"):
        seed_source(readers, source_id)
        seed_job(readers, f"job-{source_id}", source_id, status="running")
        readers.put_lock(source_id, job_id=f"job-{source_id}", lease_expires_at=at(60))
    seed_source(readers, "idle")
    seed_job(readers, "job-idle", "idle", status="succeeded")
    readers.refresh_search()

    await service.list_sources()

    assert [call.key for call in readers.behavior.calls_of("jobs.get_locks")] == ["a,b"]


async def test_a_failed_lock_read_as_a_whole_hits_every_running_row_and_no_other_row(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    for source_id in ("a", "b"):
        seed_source(readers, source_id)
        seed_job(readers, f"job-{source_id}", source_id, status="running")
        readers.put_lock(source_id, job_id=f"job-{source_id}", lease_expires_at=at(60))
    seed_source(readers, "idle")
    seed_job(readers, "job-idle", "idle", status="succeeded")
    readers.behavior.inject("jobs.get_locks", STORE_UNAVAILABLE)
    readers.refresh_search()

    items = await list_items(service)

    assert items["a"].unavailable == {"last_crawl.stalled": "store_unavailable"}
    assert items["b"].unavailable == {"last_crawl.stalled": "store_unavailable"}
    assert items["idle"].unavailable == {}
    assert items["idle"].last_crawl is not None
    assert items["idle"].last_crawl.stalled is False


async def test_a_failed_job_search_marks_every_row_and_the_delete_job_only_when_deleting(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "active-source")
    seed_source(readers, "deleting-source", status="deleting")
    seed_documents(readers, "active-source", 2)
    readers.behavior.inject("jobs.latest_by_source", STORE_UNAVAILABLE)
    readers.refresh_search()

    response = await service.list_sources()

    items = {item.source_id: item for item in response.items}
    assert items["active-source"].unavailable == {
        "last_crawl": "store_unavailable",
        "last_completed_at": "store_unavailable",
    }
    assert items["deleting-source"].unavailable == {
        "last_crawl": "store_unavailable",
        "last_completed_at": "store_unavailable",
        "delete_job": "store_unavailable",
    }
    for item in items.values():
        assert (item.last_crawl, item.last_completed_at, item.delete_job) == (None, None, None)
    # 検索インデックスの件数は、別の読み取りなので影響を受けない。
    assert items["active-source"].document_count == 2
    assert response.unavailable == {}


async def test_a_job_search_timeout_is_reported_as_a_timeout(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs")
    readers.behavior.inject("jobs.latest_by_source", STORE_TIMEOUT)
    readers.refresh_search()

    [item] = (await service.list_sources()).items

    assert item.unavailable == {"last_crawl": "timeout", "last_completed_at": "timeout"}


@pytest.mark.parametrize(
    ("failed", "reason"),
    [(SEARCH_UNAVAILABLE, "search_index_unavailable"), (SEARCH_TIMEOUT, "timeout")],
)
async def test_a_failed_count_marks_the_document_count_of_every_row(
    readers: InMemoryReaders, service: SourceCatalogService, failed: Failed, reason: str
) -> None:
    for source_id in ("a", "b"):
        seed_source(readers, source_id)
        seed_job(readers, f"job-{source_id}", source_id, status="succeeded")
    readers.behavior.inject("search_index.count_by_source", failed)
    readers.refresh_search()

    response = await service.list_sources()

    for item in response.items:
        assert item.document_count is None
        assert item.unavailable == {"document_count": reason}
        # 最新のジョブは、別の読み取りなので影響を受けない。
        assert item.last_crawl is not None
    assert response.unavailable == {}


async def test_every_failure_at_once_keeps_the_top_level_empty_and_the_rows_separate(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs")
    readers.behavior.inject("jobs.latest_by_source", STORE_UNAVAILABLE)
    readers.behavior.inject("search_index.count_by_source", SEARCH_TIMEOUT)
    readers.refresh_search()

    response = await service.list_sources()

    [item] = response.items
    assert item.unavailable == {
        "last_crawl": "store_unavailable",
        "last_completed_at": "store_unavailable",
        "document_count": "timeout",
    }
    assert response.unavailable == {}


async def test_no_key_uses_the_items_prefix_form(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs", status="deleting")
    seed_job(readers, "job-1", "docs", status="running")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(60))
    readers.behavior.inject("jobs.get_locks", STORE_UNAVAILABLE)
    readers.behavior.inject("search_index.count_by_source", SEARCH_UNAVAILABLE)
    readers.refresh_search()

    [item] = (await service.list_sources()).items

    assert item.unavailable
    assert not any(key.startswith("items") for key in item.unavailable)


# --- EP-01: stalled(C 11章 5・16) ---


async def test_an_expired_lease_is_stalled_and_not_cancellable(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs")
    seed_job(readers, "job-1", "docs", status="running")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(-1))
    readers.refresh_search()

    [item] = (await service.list_sources()).items

    assert item.last_crawl is not None
    assert (item.last_crawl.status, item.last_crawl.stalled, item.last_crawl.cancellable) == (
        JobStatus.RUNNING,
        True,
        False,
    )
    assert item.unavailable == {}


async def test_a_job_that_finished_after_the_search_snapshot_is_not_reported_as_stalled(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    """検索は古い(`running`)が、`mget` では終了・ロック解放済み。確認読みで偽陽性を避ける。"""
    seed_source(readers, "docs")
    seed_job(readers, "job-1", "docs", status="running", started_at=at(-30))
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(60))
    readers.refresh_search()
    readers.update_job("job-1", status="succeeded", finished_at=at(-1))
    readers.remove_lock("docs")

    [item] = (await service.list_sources()).items

    assert item.last_crawl is not None
    assert item.last_crawl.stalled is False
    # 行の `status` などの項目も、読み直した値にそろえる(読み直す項目は一覧の行の全項目)。
    assert item.last_crawl.status is JobStatus.SUCCEEDED
    assert (item.last_crawl.started_at, item.last_crawl.finished_at) == (at(-30), at(-1))
    assert operations(readers).count("jobs.get_jobs") == 1


async def test_a_running_job_without_its_lock_is_stalled_after_the_confirmation(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs")
    seed_job(readers, "job-1", "docs", status="running")
    readers.refresh_search()

    [item] = (await service.list_sources()).items

    assert item.last_crawl is not None
    assert item.last_crawl.stalled is True
    # 読み直した記録から作る行も、一覧の行の項目を欠かさない。
    assert (item.last_crawl.job_id, item.last_crawl.status) == ("job-1", JobStatus.RUNNING)
    assert (item.last_crawl.trigger, item.last_crawl.queued_at) == (JobTrigger.MANUAL, at(0))
    # ロック文書 → ジョブ記録の順で読み直す。
    assert operations(readers)[-3:] == ["jobs.get_locks", "jobs.get_locks", "jobs.get_jobs"]


async def test_a_failed_confirmation_read_marks_only_the_row_that_needed_it(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "a")
    seed_job(readers, "job-a", "a", status="running")
    seed_source(readers, "b")
    seed_job(readers, "job-b", "b", status="running")
    readers.put_lock("b", job_id="job-b", lease_expires_at=at(60))
    readers.fail_document("jobs.get_jobs", "job-a", STORE_UNAVAILABLE)
    readers.refresh_search()

    items = await list_items(service)

    assert items["a"].unavailable == {"last_crawl.stalled": "store_unavailable"}
    assert items["b"].unavailable == {}


async def test_the_stalled_check_of_a_deleting_source_has_its_own_relative_key(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs", status="deleting")
    seed_job(readers, "crawl-1", "docs", status="succeeded", queued_at=-9)
    seed_job(readers, "delete-1", "docs", status="running", job_type="source_delete", queued_at=-1)
    readers.put_lock("docs", job_id="delete-1", lease_expires_at=at(60))
    readers.fail_document("jobs.get_locks", "docs", STORE_TIMEOUT)
    readers.refresh_search()

    [item] = (await service.list_sources()).items

    assert item.delete_job is not None
    assert item.delete_job.stalled is None
    assert item.last_crawl is not None
    assert item.last_crawl.stalled is False
    assert item.unavailable == {"delete_job.stalled": "timeout"}


# --- EP-02 ---


async def get_source(service: SourceCatalogService, source_id: str = "docs") -> Any:
    return await service.get_source(source_id)


async def test_the_detail_has_the_settings_the_lock_the_jobs_and_the_index_count(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(
        readers,
        "docs",
        schedule_cron="0 3 * * *",
        connector_config={"root": "/data/documents/share", "exclude_patterns": ["**/draft/**"]},
        updated_at="2026-11-20T11:00:00+09:00",
        ratio_threshold=0.29,
    )
    seed_job(readers, "job-1", "docs", status="succeeded", queued_at=-100, finished_at=at(-90))
    seed_documents(readers, "docs", 4)
    readers.refresh_search()

    response = await get_source(service)

    body = response.model_dump(mode="json")
    assert body["connector_config"] == {
        "root": "/data/documents/share",
        "exclude_patterns": ["**/draft/**"],
    }
    assert {key: body[key] for key in body if key not in ("connector_config", "last_crawl")} == {
        "source_id": "docs",
        "connector_type": "file_system",
        "ttl_seconds": 2_592_000,
        "ttl_days": 30,
        "ratio_threshold_percent": 29,
        "min_delete_count": 10,
        "schedule_cron": "0 3 * * *",
        "status": "active",
        "updated_at": "2026-11-20T02:00:00.000Z",
        "lock": {"state": "none", "job": None, "acquired_at": None},
        "last_completed_at": at(-90),
        "delete_job": None,
        "index": {"document_count": 4},
        "unavailable": {},
    }
    assert body["last_crawl"]["job_id"] == "job-1"


async def test_a_lock_held_by_a_running_job_shows_the_state_and_the_job(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs")
    seed_job(readers, "job-1", "docs", status="running", trigger="schedule")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(30), acquired_at=at(-5))
    readers.refresh_search()

    response = await get_source(service)

    assert response.lock is not None
    assert response.lock.state is LockState.HELD_CRAWL
    assert response.lock.acquired_at == at(-5)
    assert response.lock.job is not None
    assert response.lock.job.model_dump(mode="json") == {
        "job_id": "job-1",
        "job_type": "crawl",
        "status": "running",
        "trigger": "schedule",
        "lease_expires_at": at(30),
    }
    assert response.last_crawl is not None
    assert response.last_crawl.stalled is False


async def test_a_failed_lock_read_is_a_null_lock_with_a_top_level_key(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs")
    readers.behavior.inject("jobs.get_locks", STORE_TIMEOUT)

    response = await get_source(service)

    assert response.lock is None
    assert response.unavailable == {"lock": "timeout"}
    # 設定は読めている。
    assert response.source_id == "docs"


async def test_a_failed_job_record_read_leaves_the_lock_with_an_unknown_state_and_no_key(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs")
    seed_job(readers, "job-1", "docs", status="running")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(30))
    readers.fail_document("jobs.get_jobs", "job-1", STORE_UNAVAILABLE)

    response = await get_source(service)

    assert response.lock is not None
    assert response.lock.state is LockState.UNKNOWN
    assert "lock" not in response.unavailable


@pytest.mark.parametrize("failed", [STORE_UNAVAILABLE, STORE_TIMEOUT])
async def test_a_failed_settings_read_is_a_503_and_nothing_else_is_read(
    readers: InMemoryReaders, service: SourceCatalogService, failed: Failed
) -> None:
    """S4 が現在値のないまま全置換しないよう、設定が取れなければ部分的な応答にしない。"""
    seed_source(readers, "docs")
    readers.behavior.inject("sources.get", failed)

    with pytest.raises(AdminApiError) as raised:
        await get_source(service)

    assert (raised.value.status_code, raised.value.code) == (503, "unavailable")
    assert operations(readers) == ["sources.get"]


async def test_a_missing_source_is_a_404_and_nothing_else_is_read(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    with pytest.raises(AdminApiError) as raised:
        await get_source(service, "never-registered")

    assert (raised.value.status_code, raised.value.code) == (404, "source_config_not_found")
    assert operations(readers) == ["sources.get"]


async def test_a_source_that_is_being_deleted_still_exists(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs", status="deleting")
    seed_job(readers, "delete-1", "docs", status="queued", job_type="source_delete")
    readers.refresh_search()

    response = await get_source(service)

    assert response.status is SourceStatus.DELETING
    assert response.delete_job is not None
    assert response.delete_job.job_id == "delete-1"


async def test_the_settings_are_read_live_not_from_the_search_snapshot(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    """EP-02 の設定は `mget`(登録・更新の直後でも見える)。"""
    seed_source(readers, "docs")

    response = await get_source(service)

    assert response.source_id == "docs"


@pytest.mark.parametrize(
    ("fields", "malformed", "nulled"),
    [
        ({"ttl": "30d"}, ["ttl_seconds"], ["ttl_seconds", "ttl_days"]),
        ({"ratio_threshold": "20%"}, ["ratio_threshold_percent"], ["ratio_threshold_percent"]),
        ({"min_delete_count": 1.5}, ["min_delete_count"], ["min_delete_count"]),
        ({"connector_config": "root"}, ["connector_config"], ["connector_config"]),
        ({"connector_type": 3}, ["connector_type"], ["connector_type"]),
        ({"status": "paused"}, ["status"], ["status"]),
        ({"updated_at": "2026-11-20T11:00:00"}, ["updated_at"], ["updated_at"]),
        ({"schedule_cron": 5}, ["schedule_cron"], ["schedule_cron"]),
    ],
)
async def test_an_unreadable_setting_is_null_with_a_malformed_key_for_that_field_only(
    readers: InMemoryReaders,
    service: SourceCatalogService,
    fields: dict[str, Any],
    malformed: list[str],
    nulled: list[str],
) -> None:
    seed_source(readers, "docs", **fields)

    response = await get_source(service)

    assert response.unavailable == dict.fromkeys(malformed, "malformed")
    for name in nulled:
        assert getattr(response, name) is None


async def test_a_job_search_failure_marks_the_top_level_and_the_delete_job_only_when_deleting(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs")
    seed_source(readers, "going", status="deleting")
    readers.behavior.inject("jobs.latest_by_source", STORE_UNAVAILABLE, times=2)
    readers.refresh_search()

    active = await get_source(service, "docs")
    deleting = await get_source(service, "going")

    assert active.unavailable == {
        "last_crawl": "store_unavailable",
        "last_completed_at": "store_unavailable",
    }
    assert deleting.unavailable == {
        "last_crawl": "store_unavailable",
        "last_completed_at": "store_unavailable",
        "delete_job": "store_unavailable",
    }


@pytest.mark.parametrize(
    ("failed", "reason"),
    [(SEARCH_UNAVAILABLE, "search_index_unavailable"), (SEARCH_TIMEOUT, "timeout")],
)
async def test_a_failed_count_is_a_null_index_count_with_the_full_path_key(
    readers: InMemoryReaders, service: SourceCatalogService, failed: Failed, reason: str
) -> None:
    """B 3.2 の例: 検索インデックスの読み取りだけが失敗した部分失敗。"""
    seed_source(readers, "docs")
    seed_job(readers, "job-1", "docs", status="succeeded")
    readers.behavior.inject("counts.count_for_source", failed)
    readers.refresh_search()

    response = await get_source(service)

    assert response.index.document_count is None
    assert response.unavailable == {"index.document_count": reason}
    assert response.lock is not None
    assert response.last_crawl is not None


async def test_a_source_without_documents_has_a_zero_count_without_a_key(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs")
    readers.refresh_search()

    response = await get_source(service)

    assert response.index.document_count == 0
    assert response.unavailable == {}


async def test_a_failed_lock_display_does_not_stop_the_stalled_check_of_the_job(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs")
    seed_job(readers, "job-1", "docs", status="running")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(60))
    # 1 回目の読み取り(ロックの表示)だけが失敗する。2 回目(`stalled` の判定)は成功する。
    readers.behavior.inject("jobs.get_locks", STORE_UNAVAILABLE, times=1)
    readers.refresh_search()

    response = await get_source(service)

    assert response.lock is None
    assert response.last_crawl is not None
    assert response.last_crawl.stalled is False
    assert response.unavailable == {"lock": "store_unavailable"}


async def test_the_lock_is_read_before_the_job_records_and_the_count_last(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs")
    seed_job(readers, "job-1", "docs", status="running")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(60))
    readers.refresh_search()

    await get_source(service)

    assert operations(readers) == [
        "sources.get",
        "jobs.get_locks",
        "jobs.get_jobs",
        "jobs.latest_by_source",
        "jobs.get_locks",
        "counts.count_for_source",
    ]


async def test_a_job_that_finished_after_the_search_snapshot_is_shown_as_finished_in_the_detail(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    """EP-02 でも、検索は古い(`running`)が `mget` では終了・ロック解放済み。偽陽性にしない。"""
    seed_source(readers, "docs")
    seed_job(readers, "job-1", "docs", status="running", started_at=at(-30))
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(60))
    readers.refresh_search()
    readers.update_job("job-1", status="succeeded", finished_at=at(-1))
    readers.remove_lock("docs")

    response = await get_source(service)

    assert response.last_crawl is not None
    assert (response.last_crawl.stalled, response.last_crawl.cancellable) == (False, False)
    assert response.last_crawl.status is JobStatus.SUCCEEDED
    assert response.last_crawl.finished_at == at(-1)
    assert response.lock is not None
    assert response.lock.state is LockState.NONE
    assert response.unavailable == {}


async def test_a_failed_lock_document_marks_both_the_lock_and_the_stalled_flag(
    readers: InMemoryReaders, service: SourceCatalogService
) -> None:
    seed_source(readers, "docs")
    seed_job(readers, "job-1", "docs", status="running")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(60))
    readers.fail_document("jobs.get_locks", "docs", STORE_TIMEOUT)
    readers.refresh_search()

    response = await get_source(service)

    assert response.lock is None
    assert response.last_crawl is not None
    assert (response.last_crawl.stalled, response.last_crawl.cancellable) == (None, False)
    assert response.unavailable == {"lock": "timeout", "last_crawl.stalled": "timeout"}
