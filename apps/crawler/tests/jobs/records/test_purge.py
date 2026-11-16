"""記録の整理・一括削除(architecture 6.4・8.1 の順 3。テスト観点 #24・#33・#37 の単体部分)。

10,001 件以上・実 PIT・実バルク削除の部分失敗は、実 OpenSearch の統合テストで確認する(#37)。
ここは分岐(走査の単位・並べ替え・やり直し・部分失敗の再送)を、fake で確かめる。
"""

import pytest

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.common.retry import Retrier
from loreley_crawler.infrastructure.opensearch import RepositorySettings, SortKey
from loreley_crawler.jobs.records import (
    DocumentRecordType,
    StoreWriteFailedError,
    delete_document_records_of_source,
    purge_document_records,
)
from tests.fakes import in_memory_repository as ops
from tests.jobs.records.support import (
    NO_WAIT_RETRIER,
    SpyRepository,
    seed_document_record,
)

SKIP = DocumentRecordType.SKIP
OVERSIZE = DocumentRecordType.OVERSIZE


class Cancelled(Exception):
    pass


def seed_two_sources(repository: SpyRepository) -> None:
    """`docs` の skip・oversize(同じ `document_id` が共存)と、別のソース・別の種類の記録。"""
    for document_id in ("d1", "d2", "d3"):
        seed_document_record(repository, "skip", "docs", document_id)
        seed_document_record(repository, "oversize", "docs", document_id)
        seed_document_record(repository, "skip", "other", document_id)
    repository.seed("lock-docs", {"record_type": "lock", "source_id": "docs", "owner": "o"})
    repository.seed("job-1", {"record_type": "job", "source_id": "docs", "job_type": "crawl"})
    repository.seed("maintenance", {"enabled": False})


# --- 走査の単位と並べ替え(0007 §4-1) ---


def test_each_record_type_is_scanned_once_by_its_own_scan_sorted_by_a_unique_document_id() -> None:
    repository = SpyRepository()
    seed_two_sources(repository)

    delete_document_records_of_source(repository, NO_WAIT_RETRIER, source_id="docs")

    scanned = [
        (flt.equals["record_type"], flt.equals["source_id"], sort) for flt, sort in repository.scans
    ]
    assert sorted(scanned) == [
        ("oversize", "docs", (SortKey("document_id"),)),
        ("skip", "docs", (SortKey("document_id"),)),
    ]
    # `sort` が一意な `document_id` で終わる(ページ境界の同値の取りこぼしを避ける)。
    assert all(sort[-1].field_name == "document_id" for _filter, sort in repository.scans)


def test_a_cleanup_scan_also_sorts_by_document_id_within_one_record_type() -> None:
    repository = SpyRepository()
    seed_two_sources(repository)

    purge_document_records(
        repository,
        NO_WAIT_RETRIER,
        source_id="docs",
        record_type=SKIP,
        should_delete=lambda _: True,
    )

    assert len(repository.scans) == 1
    record_filter, sort = repository.scans[0]
    assert record_filter.equals == {"record_type": "skip", "source_id": "docs"}
    assert sort[-1].field_name == "document_id"


# --- 対象の選択と削除 ---


def test_source_deletion_removes_only_that_sources_skip_and_oversize_records() -> None:
    repository = SpyRepository()
    seed_two_sources(repository)

    deleted = delete_document_records_of_source(repository, NO_WAIT_RETRIER, source_id="docs")

    assert deleted == 6
    assert repository.record_ids() == [
        "job-1",
        "lock-docs",
        "maintenance",
        "skip-other-d1",
        "skip-other-d2",
        "skip-other-d3",
    ]
    assert repository.open_scan_count == 0


def test_source_deletion_with_no_records_succeeds_without_a_bulk_delete() -> None:
    repository = SpyRepository()
    repository.seed("lock-docs", {"record_type": "lock"})

    assert delete_document_records_of_source(repository, NO_WAIT_RETRIER, source_id="docs") == 0

    assert repository.deleted_id_batches == []


def test_source_deletion_is_idempotent_on_a_rerun() -> None:
    repository = SpyRepository()
    seed_two_sources(repository)

    delete_document_records_of_source(repository, NO_WAIT_RETRIER, source_id="docs")
    assert delete_document_records_of_source(repository, NO_WAIT_RETRIER, source_id="docs") == 0


def test_source_deletion_removes_records_whose_fields_are_malformed_too() -> None:
    repository = SpyRepository()
    repository.seed("skip-docs-x", {"record_type": "skip", "source_id": "docs"})  # document_id なし

    delete_document_records_of_source(repository, NO_WAIT_RETRIER, source_id="docs")

    assert repository.record_ids() == []


def test_cleanup_deletes_only_the_records_the_caller_selects_by_document_id() -> None:
    repository = SpyRepository()
    seed_two_sources(repository)

    deleted = purge_document_records(
        repository,
        NO_WAIT_RETRIER,
        source_id="docs",
        record_type=SKIP,
        should_delete=lambda document_id: document_id in {"d1", "d3"},
    )

    assert deleted == 2
    remaining = repository.record_ids()
    assert "skip-docs-d2" in remaining
    assert "skip-docs-d1" not in remaining
    assert "skip-docs-d3" not in remaining
    # 別の種類・別のソースの記録は対象外。
    assert {"oversize-docs-d1", "oversize-docs-d2", "oversize-docs-d3"} <= set(remaining)
    assert {"skip-other-d1", "skip-other-d2", "skip-other-d3"} <= set(remaining)


def test_cleanup_leaves_a_record_whose_document_id_cannot_be_read() -> None:
    repository = SpyRepository()
    repository.seed("skip-docs-x", {"record_type": "skip", "source_id": "docs"})
    seed_document_record(repository, "skip", "docs", "d1")

    purge_document_records(
        repository,
        NO_WAIT_RETRIER,
        source_id="docs",
        record_type=SKIP,
        should_delete=lambda _: True,
    )

    assert repository.record_ids() == ["skip-docs-x"]


def test_cleanup_keeps_every_record_when_the_caller_selects_none() -> None:
    repository = SpyRepository()
    seed_two_sources(repository)
    before = repository.record_ids()

    deleted = purge_document_records(
        repository,
        NO_WAIT_RETRIER,
        source_id="docs",
        record_type=OVERSIZE,
        should_delete=lambda _: False,
    )

    assert deleted == 0
    assert repository.record_ids() == before
    assert repository.deleted_id_batches == []


def test_many_records_across_several_pages_are_all_removed() -> None:
    repository = SpyRepository(RepositorySettings(scan_page_size=100, bulk_delete_batch_size=100))
    for number in range(350):
        seed_document_record(repository, "skip", "docs", f"d{number:04d}")
        seed_document_record(repository, "oversize", "docs", f"d{number:04d}")
    seed_document_record(repository, "skip", "other", "d0000")

    deleted = delete_document_records_of_source(repository, NO_WAIT_RETRIER, source_id="docs")

    assert deleted == 700
    assert repository.record_ids() == ["skip-other-d0000"]
    assert repository.open_scan_count == 0


# --- 走査全体のやり直し(0007 §4-2) ---


def test_an_expired_pit_restarts_the_whole_scan_and_still_deletes_everything() -> None:
    repository = SpyRepository()
    seed_two_sources(repository)
    repository.behavior.inject(ops.SCAN_PAGE, StoreUnavailableError("pit_expired"))

    deleted = delete_document_records_of_source(repository, NO_WAIT_RETRIER, source_id="docs")

    assert deleted == 6
    # skip の走査が 1 回やり直された(skip 2 回 + oversize 1 回)。
    scanned_types = [flt.equals["record_type"] for flt, _sort in repository.scans]
    assert sorted(scanned_types) == ["oversize", "skip", "skip"]
    assert repository.open_scan_count == 0
    assert repository.record_ids() == [
        "job-1",
        "lock-docs",
        "maintenance",
        "skip-other-d1",
        "skip-other-d2",
        "skip-other-d3",
    ]


def test_nothing_is_deleted_when_the_scan_keeps_failing() -> None:
    repository = SpyRepository()
    seed_two_sources(repository)
    before = repository.record_ids()
    repository.behavior.inject(ops.SCAN_PAGE, StoreUnavailableError("pit_expired"), times=None)

    with pytest.raises(StoreUnavailableError) as raised:
        delete_document_records_of_source(repository, NO_WAIT_RETRIER, source_id="docs")

    assert raised.value.reason == "pit_expired"
    assert len(repository.scans) == 3  # 試行 3 回
    assert repository.deleted_id_batches == []
    assert repository.record_ids() == before
    assert repository.open_scan_count == 0


def test_a_failure_to_start_the_scan_is_retried_too() -> None:
    repository = SpyRepository()
    seed_document_record(repository, "skip", "docs", "d1")
    repository.behavior.inject(ops.SCAN, StoreUnavailableError("search_incomplete"))

    deleted = purge_document_records(
        repository,
        NO_WAIT_RETRIER,
        source_id="docs",
        record_type=SKIP,
        should_delete=lambda _: True,
    )

    assert deleted == 1


def test_an_unexpected_response_is_not_retried() -> None:
    repository = SpyRepository()
    seed_document_record(repository, "skip", "docs", "d1")
    repository.behavior.inject(
        ops.SCAN_PAGE, StoreUnexpectedResponseError("non_unique_sort"), times=None
    )

    with pytest.raises(StoreUnexpectedResponseError):
        purge_document_records(
            repository,
            NO_WAIT_RETRIER,
            source_id="docs",
            record_type=SKIP,
            should_delete=lambda _: True,
        )

    assert len(repository.scans) == 1
    assert repository.open_scan_count == 0


def test_the_checkpoint_can_interrupt_the_retry() -> None:
    repository = SpyRepository()
    seed_document_record(repository, "skip", "docs", "d1")
    repository.behavior.inject(ops.SCAN_PAGE, StoreUnavailableError("pit_expired"), times=None)
    calls: list[int] = []

    def checkpoint() -> None:
        calls.append(1)
        if len(calls) >= 2:
            raise Cancelled

    retrier = Retrier(
        NO_WAIT_RETRIER.policy,
        checkpoint=checkpoint,
        sleep=lambda _seconds: None,
        wait_slice_seconds=1_000,
    )

    with pytest.raises(Cancelled):
        purge_document_records(
            repository, retrier, source_id="docs", record_type=SKIP, should_delete=lambda _: True
        )


# --- バルク削除の部分失敗(0007 §4・architecture 3.1) ---


def test_a_partial_failure_resends_only_the_failed_ids() -> None:
    repository = SpyRepository()
    seed_two_sources(repository)
    repository.fail_bulk_delete_of(["skip-docs-d2", "oversize-docs-d3"], times=1)

    deleted = delete_document_records_of_source(repository, NO_WAIT_RETRIER, source_id="docs")

    assert deleted == 6
    # skip の削除(d1〜d3 の 3 件 → 失敗した d2 だけ再送)と、oversize の同様の流れ。
    batches = [set(batch) for batch in repository.deleted_id_batches]
    assert batches == [
        {"skip-docs-d1", "skip-docs-d2", "skip-docs-d3"},
        {"skip-docs-d2"},
        {"oversize-docs-d1", "oversize-docs-d2", "oversize-docs-d3"},
        {"oversize-docs-d3"},
    ]
    assert [r for r in repository.record_ids() if "docs" in r and "other" not in r] == ["lock-docs"]


def test_a_partial_failure_that_persists_becomes_a_store_write_failure() -> None:
    repository = SpyRepository()
    for document_id in ("d1", "d2", "d3"):
        seed_document_record(repository, "skip", "docs", document_id)
    repository.fail_bulk_delete_of(["skip-docs-d2"], times=None)

    with pytest.raises(StoreWriteFailedError) as raised:
        purge_document_records(
            repository,
            NO_WAIT_RETRIER,
            source_id="docs",
            record_type=SKIP,
            should_delete=lambda _: True,
        )

    assert isinstance(raised.value, StoreUnavailableError)  # `store_unavailable` として扱われる
    assert raised.value.reason == "bulk_delete_incomplete"
    # 試行 3 回。2 回目以降は失敗した ID だけ。成功した ID は消えている。
    assert [set(batch) for batch in repository.deleted_id_batches] == [
        {"skip-docs-d1", "skip-docs-d2", "skip-docs-d3"},
        {"skip-docs-d2"},
        {"skip-docs-d2"},
    ]
    assert repository.record_ids() == ["skip-docs-d2"]


def test_a_whole_bulk_delete_failure_is_retried_with_the_same_ids() -> None:
    repository = SpyRepository()
    for document_id in ("d1", "d2"):
        seed_document_record(repository, "skip", "docs", document_id)
    repository.behavior.inject(ops.DELETE_IDS, StoreUnavailableError("timeout"))

    deleted = purge_document_records(
        repository,
        NO_WAIT_RETRIER,
        source_id="docs",
        record_type=SKIP,
        should_delete=lambda _: True,
    )

    assert deleted == 2
    assert repository.record_ids() == []
    assert len(repository.scans) == 1  # 走査はやり直さない


def test_the_bulk_delete_failure_stops_before_the_next_record_type() -> None:
    repository = SpyRepository()
    seed_document_record(repository, "skip", "docs", "d1")
    seed_document_record(repository, "oversize", "docs", "d1")
    repository.fail_bulk_delete_of(["skip-docs-d1"], times=None)

    with pytest.raises(StoreWriteFailedError):
        delete_document_records_of_source(repository, NO_WAIT_RETRIER, source_id="docs")

    assert "oversize-docs-d1" in repository.record_ids()  # 失敗したので、ジョブは先へ進まない
