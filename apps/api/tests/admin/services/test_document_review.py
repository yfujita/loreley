"""文書の確認(EP-11。C 11章 6・7・16)。

読み取りは偽の Reader(`InMemoryReaders`。検索は古いスナップショット)で、障害を注入して確かめる。
行ごとの成否(`existence` は全行、`tab_counts.<タブ>`・`document_count` は最上位)の帰属が中心。
"""

from datetime import timedelta
from typing import Any

import pytest

from loreley_api.admin.base.codes import DocumentExistence, DocumentTab
from loreley_api.admin.base.errors import AdminApiError
from loreley_api.admin.schemas.documents import DocumentListResponse
from loreley_api.admin.services.document_review import DocumentReviewService
from loreley_api.common.results import Failed
from loreley_api.common.timestamps import format_instant
from tests.admin.factories import make_admin_dependencies
from tests.fakes.clock import DEFAULT_NOW as NOW
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_readers import STORE_TIMEOUT, STORE_UNAVAILABLE, InMemoryReaders
from tests.fakes.inline_runner import InlineRunner

pytestmark = pytest.mark.anyio

SEARCH_UNAVAILABLE = Failed(
    kind="unavailable", target="search_index", error_class_name="ConnectionError"
)
SEARCH_TIMEOUT = Failed(kind="timeout", target="search_index", error_class_name="ConnectionTimeout")

SKIPPED = DocumentTab.SKIPPED
EXTRACT_FAILED = DocumentTab.EXTRACT_FAILED
OVERSIZE = DocumentTab.OVERSIZE
SUMMARY_PENDING = DocumentTab.SUMMARY_PENDING


def at(seconds_from_now: float) -> str:
    return format_instant(NOW + timedelta(seconds=seconds_from_now))


@pytest.fixture
def service(
    readers: InMemoryReaders, fixed_clock: FixedClock, inline_runner: InlineRunner
) -> DocumentReviewService:
    return make_admin_dependencies(readers, fixed_clock, inline_runner).document_review


@pytest.fixture(autouse=True)
def source(readers: InMemoryReaders) -> None:
    readers.put_source("docs")


async def list_tab(
    service: DocumentReviewService,
    tab: DocumentTab,
    *,
    source_id: str = "docs",
    page: int = 1,
    items_per_page: int = 25,
    descending: bool = True,
) -> DocumentListResponse:
    return await service.list_documents(
        source_id=source_id,
        tab=tab,
        page=page,
        items_per_page=items_per_page,
        descending=descending,
    )


def operations(readers: InMemoryReaders) -> list[str]:
    return [call.operation for call in readers.behavior.calls]


def seed_skip(
    readers: InMemoryReaders, document_id: str, *, last_skipped_at: float = 0, **fields: Any
) -> None:
    defaults: dict[str, Any] = {
        "external_id": f"files/{document_id}.pdf",
        "stage": "fetch",
        "reason": "fetch_permission_denied: 取得の権限がなかった",
        "attempts": 3,
        "consecutive_skips": 5,
        "first_skipped_at": at(-1000),
        "last_skipped_at": at(last_skipped_at),
        "last_job_id": "job-1",
    }
    readers.put_skip("docs", document_id, **{**defaults, **fields})


def seed_indexed(
    readers: InMemoryReaders, document_id: str, *, source_id: str = "docs", **fields: Any
) -> None:
    readers.put_document(document_id, source_id=source_id, index_status="indexed", **fields)


# --- 形 ---


async def test_the_skipped_tab_returns_the_rows_and_all_the_counts(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    seed_skip(readers, "doc-1", last_skipped_at=-10)
    seed_skip(readers, "doc-2", last_skipped_at=-20)
    seed_indexed(readers, "doc-1")
    readers.put_document("doc-x", source_id="docs", index_status="extract_failed")
    readers.put_oversize("docs", "doc-big")
    readers.refresh_search()

    response = await list_tab(service, SKIPPED)

    body = response.model_dump(mode="json")
    assert body["tab"] == "skipped"
    assert body["items"] == [
        {
            "document_id": "doc-1",
            "external_id": "files/doc-1.pdf",
            "stage": "fetch",
            "reason": "fetch_permission_denied: 取得の権限がなかった",
            "attempts": 3,
            "consecutive_skips": 5,
            "first_skipped_at": at(-1000),
            "last_skipped_at": at(-10),
            "last_job_id": "job-1",
            "existence": "existing",
            "unavailable": {},
        },
        {
            "document_id": "doc-2",
            "external_id": "files/doc-2.pdf",
            "stage": "fetch",
            "reason": "fetch_permission_denied: 取得の権限がなかった",
            "attempts": 3,
            "consecutive_skips": 5,
            "first_skipped_at": at(-1000),
            "last_skipped_at": at(-20),
            "last_job_id": "job-1",
            "existence": "new",
            "unavailable": {},
        },
    ]
    assert (body["total"], body["page"], body["items_per_page"], body["window_limit"]) == (
        2,
        1,
        25,
        10_000,
    )
    assert body["tab_counts"] == {
        "skipped": 2,
        "extract_failed": 1,
        "oversize": 1,
        "summary_pending": 0,
    }
    # 登録文書数は `index_status` を問わない(抽出失敗も数える)。
    assert body["document_count"] == 2
    assert body["unavailable"] == {}


async def test_the_extract_failed_tab_takes_the_document_id_from_the_index_id(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    readers.put_document(
        "doc-1",
        source_id="docs",
        index_status="extract_failed",
        title=None,
        external_id="broken.pdf",
        mime_type="application/pdf",
        size=2048,
        source_updated_at=at(-500),
        last_seen_at=at(-5),
    )
    seed_indexed(readers, "doc-ok")
    readers.put_document("other", source_id="elsewhere", index_status="extract_failed")
    readers.refresh_search()

    response = await list_tab(service, EXTRACT_FAILED)

    assert [row.model_dump(mode="json") for row in response.items] == [
        {
            "document_id": "doc-1",
            "title": None,
            "external_id": "broken.pdf",
            "mime_type": "application/pdf",
            "size": 2048,
            "source_updated_at": at(-500),
            "last_seen_at": at(-5),
            "unavailable": {},
        }
    ]
    assert response.total == 1
    # 要求したタブの件数は、一覧の `total` と同じ。
    assert response.tab_counts.extract_failed == 1
    assert response.document_count == 2


async def test_the_oversize_tab_lists_the_records_of_the_source(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    readers.put_oversize(
        "docs",
        "doc-big",
        external_id="big.bin",
        detected_by="indexer",
        size=70_000,
        first_detected_at=at(-100),
        last_detected_at=at(-10),
        last_job_id="job-2",
    )
    readers.put_oversize(
        "docs", "doc-unknown-size", detected_by="crawler", last_detected_at=at(-20)
    )
    readers.put_oversize("elsewhere", "doc-other", last_detected_at=at(-1))
    readers.refresh_search()

    response = await list_tab(service, OVERSIZE)

    assert [(row.document_id, row.detected_by, row.size) for row in response.items] == [  # type: ignore[union-attr]
        ("doc-big", "indexer", 70_000),
        ("doc-unknown-size", "crawler", None),
    ]
    assert response.tab_counts.oversize == 2


async def test_the_summary_pending_tab_lists_only_pending_documents(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    readers.put_document(
        "doc-1",
        source_id="docs",
        index_status="indexed",
        summary_status="pending",
        title="議事録",
        external_id="minutes.md",
        mime_type="text/markdown",
        source_updated_at=at(-300),
        indexed_at=at(-60),
    )
    readers.put_document("doc-2", source_id="docs", index_status="indexed", summary_status="done")
    readers.refresh_search()

    response = await list_tab(service, SUMMARY_PENDING)

    assert [row.model_dump(mode="json") for row in response.items] == [
        {
            "document_id": "doc-1",
            "title": "議事録",
            "external_id": "minutes.md",
            "mime_type": "text/markdown",
            "source_updated_at": at(-300),
            "indexed_at": at(-60),
            "unavailable": {},
        }
    ]
    assert response.tab_counts.summary_pending == 1
    assert response.tab_counts.skipped == 0


async def test_an_empty_source_has_every_count_at_zero(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    for tab in DocumentTab:
        response = await list_tab(service, tab)

        assert response.items == []
        assert response.total == 0
        assert response.tab_counts.model_dump() == dict.fromkeys((t.value for t in DocumentTab), 0)
        assert response.document_count == 0
        assert response.unavailable == {}


# --- ページング・並び(C 11章 7) ---


async def test_the_default_order_is_newest_first_and_ties_are_broken_by_document_id(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    seed_skip(readers, "doc-b", last_skipped_at=0)
    seed_skip(readers, "doc-a", last_skipped_at=0)
    seed_skip(readers, "doc-old", last_skipped_at=-100)
    readers.refresh_search()

    descending = await list_tab(service, SKIPPED, descending=True)
    ascending = await list_tab(service, SKIPPED, descending=False)

    assert [row.document_id for row in descending.items] == ["doc-a", "doc-b", "doc-old"]  # type: ignore[union-attr]
    # 昇順にしても、同順位は ID の昇順のまま(取りこぼし・重複を避ける)。
    assert [row.document_id for row in ascending.items] == ["doc-old", "doc-a", "doc-b"]  # type: ignore[union-attr]


async def test_pages_do_not_overlap_and_the_total_covers_all_the_pages(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    for number in range(60):
        # 3 件ずつ同じ時刻にして、同順位が複数のページにまたがるようにする。
        seed_skip(readers, f"doc-{number:02d}", last_skipped_at=-(number // 3))
    readers.refresh_search()

    pages = [
        await list_tab(service, SKIPPED, page=number, items_per_page=25) for number in (1, 2, 3)
    ]

    seen = [row.document_id for page in pages for row in page.items]  # type: ignore[union-attr]
    assert len(seen) == 60
    assert len(set(seen)) == 60
    assert [page.total for page in pages] == [60, 60, 60]
    assert [len(page.items) for page in pages] == [25, 25, 10]
    assert (pages[1].page, pages[1].items_per_page) == (2, 25)


# --- existence(skipped タブ) ---


async def test_existence_is_one_bulk_lookup_of_the_ids_on_the_page(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    for number in range(30):
        seed_skip(readers, f"doc-{number:02d}", last_skipped_at=-number)
    seed_indexed(readers, "doc-00")
    seed_indexed(readers, "doc-29")  # 2 ページ目の行(1 ページ目の問い合わせには含まれない)
    readers.refresh_search()

    response = await list_tab(service, SKIPPED, items_per_page=25)

    [lookup] = readers.behavior.calls_of("search_index.existing_ids")
    assert lookup.key is not None
    assert lookup.key.split(",") == [f"doc-{number:02d}" for number in range(25)]
    existence = {row.document_id: row.existence for row in response.items}  # type: ignore[union-attr]
    assert existence["doc-00"] is DocumentExistence.EXISTING
    assert existence["doc-01"] is DocumentExistence.NEW


async def test_the_lookup_never_exceeds_one_hundred_ids(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    for number in range(150):
        seed_skip(readers, f"doc-{number:03d}", last_skipped_at=-number)
    readers.refresh_search()

    response = await list_tab(service, SKIPPED, items_per_page=100)

    [lookup] = readers.behavior.calls_of("search_index.existing_ids")
    assert lookup.key is not None
    assert len(lookup.key.split(",")) == 100
    assert len(response.items) == 100


async def test_an_empty_page_does_not_look_anything_up(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    await list_tab(service, SKIPPED)

    assert "search_index.existing_ids" not in operations(readers)


async def test_a_row_whose_document_id_is_unreadable_is_unknown_without_a_key(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    seed_skip(readers, "doc-1", last_skipped_at=-1)
    seed_indexed(readers, "doc-1")
    readers.put_jobs_document(
        "skip-docs-bad", record_type="skip", source_id="docs", last_skipped_at=at(-2)
    )
    readers.refresh_search()

    response = await list_tab(service, SKIPPED)

    rows = {row.document_id: row for row in response.items}  # type: ignore[union-attr]
    assert rows["doc-1"].existence is DocumentExistence.EXISTING  # type: ignore[union-attr]
    assert rows[None].existence is DocumentExistence.UNKNOWN  # type: ignore[union-attr]
    assert rows[None].unavailable == {}


async def test_a_page_without_any_readable_id_does_not_look_anything_up(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    readers.put_jobs_document(
        "skip-docs-bad", record_type="skip", source_id="docs", last_skipped_at=at(-2)
    )
    readers.refresh_search()

    response = await list_tab(service, SKIPPED)

    assert [row.existence for row in response.items] == [DocumentExistence.UNKNOWN]  # type: ignore[union-attr]
    assert "search_index.existing_ids" not in operations(readers)


async def test_existence_follows_the_search_snapshot_not_the_live_index(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    """検索は古い。登録の直後(次の検索の更新の前)は、まだ `new` に見える(C 3.2)。"""
    seed_skip(readers, "doc-1")
    readers.refresh_search()
    seed_indexed(readers, "doc-1")

    response = await list_tab(service, SKIPPED)

    assert response.items[0].existence is DocumentExistence.NEW  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("failed", "reason"),
    [(SEARCH_UNAVAILABLE, "search_index_unavailable"), (SEARCH_TIMEOUT, "timeout")],
)
async def test_a_failed_lookup_makes_every_row_unknown_and_marks_every_row(
    readers: InMemoryReaders, service: DocumentReviewService, failed: Failed, reason: str
) -> None:
    for number in range(3):
        seed_skip(readers, f"doc-{number}", last_skipped_at=-number)
        seed_indexed(readers, f"doc-{number}")
    readers.behavior.inject("search_index.existing_ids", failed)
    readers.refresh_search()

    response = await list_tab(service, SKIPPED)

    assert [row.existence for row in response.items] == [DocumentExistence.UNKNOWN] * 3  # type: ignore[union-attr]
    assert [row.unavailable for row in response.items] == [{"existence": reason}] * 3
    # `existence` は行の項目。最上位には載せず、ページ全体は返す。
    assert response.unavailable == {}
    assert response.total == 3
    assert response.tab_counts.skipped == 3


async def test_the_other_tabs_have_no_existence_and_always_empty_row_failures(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    readers.put_document("doc-1", source_id="docs", index_status="extract_failed")
    readers.put_oversize("docs", "doc-2")
    readers.put_document(
        "doc-3", source_id="docs", index_status="indexed", summary_status="pending"
    )
    readers.behavior.inject("search_index.existing_ids", SEARCH_UNAVAILABLE, times=None)
    readers.refresh_search()

    for tab in (EXTRACT_FAILED, OVERSIZE, SUMMARY_PENDING):
        response = await list_tab(service, tab)

        assert [row.unavailable for row in response.items] == [{}]
        assert not hasattr(response.items[0], "existence")
    assert "search_index.existing_ids" not in operations(readers)


# --- tab_counts・document_count の失敗(最上位) ---


async def test_a_failed_count_is_a_null_with_the_top_level_key_of_that_tab_only(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    """B 6.1 の例: `summary_pending` の件数だけが検索インデックスの失敗で取れない。"""
    seed_skip(readers, "doc-1")
    readers.put_document("doc-x", source_id="docs", index_status="extract_failed")
    readers.put_oversize("docs", "doc-big")
    readers.fail_document("counts.count_for_source", "summary_pending", SEARCH_UNAVAILABLE)
    readers.refresh_search()

    response = await list_tab(service, SKIPPED)

    assert response.tab_counts.model_dump() == {
        "skipped": 1,
        "extract_failed": 1,
        "oversize": 1,
        "summary_pending": None,
    }
    assert response.document_count == 1
    assert response.unavailable == {"tab_counts.summary_pending": "search_index_unavailable"}
    # 行には載せない。
    assert [row.unavailable for row in response.items] == [{}]


async def test_the_reason_of_a_count_follows_the_store_of_that_count(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    readers.fail_document("counts.count_for_source", "skipped", STORE_UNAVAILABLE)
    readers.fail_document("counts.count_for_source", "oversize", STORE_TIMEOUT)
    readers.fail_document("counts.count_for_source", "document_count", SEARCH_TIMEOUT)

    response = await list_tab(service, SUMMARY_PENDING)

    assert response.unavailable == {
        "tab_counts.skipped": "store_unavailable",
        "tab_counts.oversize": "timeout",
        "document_count": "timeout",
    }
    assert response.tab_counts.summary_pending == 0
    assert response.tab_counts.extract_failed == 0


async def test_a_failed_batch_of_counts_marks_every_count_except_the_listed_tab(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    readers.behavior.inject("counts.count_for_source", SEARCH_UNAVAILABLE)

    response = await list_tab(service, EXTRACT_FAILED)

    assert response.tab_counts.model_dump() == {
        "skipped": None,
        "extract_failed": 0,
        "oversize": None,
        "summary_pending": None,
    }
    assert response.document_count is None
    assert sorted(response.unavailable) == [
        "document_count",
        "tab_counts.oversize",
        "tab_counts.skipped",
        "tab_counts.summary_pending",
    ]


async def test_the_count_of_the_requested_tab_is_the_list_total_and_is_not_read_again(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    seed_skip(readers, "doc-1")
    readers.fail_document("counts.count_for_source", "skipped", STORE_UNAVAILABLE)
    readers.refresh_search()

    response = await list_tab(service, SKIPPED)

    assert response.tab_counts.skipped == 1
    assert response.unavailable == {}


# --- 主たる読み取り ---


@pytest.mark.parametrize("failed", [STORE_UNAVAILABLE, STORE_TIMEOUT])
async def test_a_failed_existence_check_of_the_source_is_a_503_and_nothing_else_is_read(
    readers: InMemoryReaders, service: DocumentReviewService, failed: Failed
) -> None:
    readers.behavior.inject("sources.get", failed)

    with pytest.raises(AdminApiError) as raised:
        await list_tab(service, SKIPPED)

    assert (raised.value.status_code, raised.value.code) == (503, "unavailable")
    assert operations(readers) == ["sources.get"]


async def test_a_missing_source_is_a_404_and_nothing_else_is_read(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    with pytest.raises(AdminApiError) as raised:
        await list_tab(service, SKIPPED, source_id="never-registered")

    assert (raised.value.status_code, raised.value.code) == (404, "source_config_not_found")
    assert operations(readers) == ["sources.get"]


async def test_a_source_that_is_being_deleted_is_still_listed(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    readers.put_source("going", status="deleting")

    response = await list_tab(service, SKIPPED, source_id="going")

    assert response.total == 0


@pytest.mark.parametrize(
    ("tab", "operation", "failed"),
    [
        (SKIPPED, "jobs.list_skipped", STORE_UNAVAILABLE),
        (OVERSIZE, "jobs.list_oversize", STORE_TIMEOUT),
        (EXTRACT_FAILED, "search_index.list_extract_failed", SEARCH_UNAVAILABLE),
        (SUMMARY_PENDING, "search_index.list_summary_pending", SEARCH_TIMEOUT),
    ],
)
async def test_a_failed_list_is_a_503_and_the_counts_are_not_read(
    readers: InMemoryReaders,
    service: DocumentReviewService,
    tab: DocumentTab,
    operation: str,
    failed: Failed,
) -> None:
    readers.behavior.inject(operation, failed)

    with pytest.raises(AdminApiError) as raised:
        await list_tab(service, tab)

    assert (raised.value.status_code, raised.value.code) == (503, "unavailable")
    assert operations(readers) == ["sources.get", operation]


async def test_the_reads_run_in_order_settings_list_counts_then_existence(
    readers: InMemoryReaders, service: DocumentReviewService
) -> None:
    seed_skip(readers, "doc-1")
    readers.refresh_search()

    await list_tab(service, SKIPPED)

    assert operations(readers) == [
        "sources.get",
        "jobs.list_skipped",
        "counts.count_for_source",
        "search_index.existing_ids",
    ]


async def test_every_read_goes_through_the_opensearch_category(
    readers: InMemoryReaders, service: DocumentReviewService, inline_runner: InlineRunner
) -> None:
    seed_skip(readers, "doc-1")
    readers.refresh_search()

    await list_tab(service, SKIPPED)

    assert inline_runner.categories == ["opensearch"] * 4
