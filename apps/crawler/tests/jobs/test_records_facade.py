"""`jobs` 入口の記録操作のファサード(`DocumentRecords`・`JobHistory`。module 4.4)。

`crawl`・`source_delete` は `Repository` を import できないため、`jobs` が内部に束ねて公開する。
どの操作も、Store 層全体の異常は渡された `Retrier` でリトライを尽くしてから送出する。
"""

import pytest

from loreley_crawler import jobs
from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.infrastructure.opensearch import Repository
from loreley_crawler.jobs import (
    DocumentRecords,
    DocumentRecordType,
    JobHistory,
    OversizeDetector,
    PreviousCrawl,
    SkipStage,
    StoreWriteFailedError,
)
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_repository import InMemoryRepository
from tests.jobs.records.support import NO_WAIT_RETRIER, job_fields

JOB_ID = "job-20261113T000000Z-00000001"
DOCUMENT_ID = "a" * 64


def make_records() -> tuple[DocumentRecords, InMemoryRepository]:
    repository = InMemoryRepository()
    return DocumentRecords(repository, FixedClock()), repository


def skip(
    records: DocumentRecords, *, source_id: str = "docs", document_id: str = DOCUMENT_ID
) -> None:
    records.record_skip(
        job_id=JOB_ID,
        source_id=source_id,
        document_id=document_id,
        external_id="a.txt",
        stage=SkipStage.FETCH,
        reason="fetch_not_found: 取得時に文書が見つからなかった",
        attempts=1,
        retrier=NO_WAIT_RETRIER,
    )


def test_the_public_names_of_the_facade_are_exported_from_the_jobs_entry() -> None:
    for name in [
        "DocumentRecords",
        "JobHistory",
        "SkipStage",
        "OversizeDetector",
        "DocumentRecordType",
        "StoreWriteFailedError",
        "PreviousCrawl",
        "loggable_id",
    ]:
        assert name in jobs.__all__
        assert hasattr(jobs, name)


def test_the_facades_expose_only_methods_and_no_repository() -> None:
    records, _ = make_records()
    history = JobHistory(InMemoryRepository())

    for facade in (records, history):
        public = {name: getattr(facade, name) for name in dir(facade) if not name.startswith("_")}
        assert public
        assert all(callable(member) for member in public.values())
        assert not any(isinstance(member, Repository) for member in public.values())


def test_a_skip_is_recorded_with_the_given_values() -> None:
    records, repository = make_records()

    skip(records)

    record = repository.body_of(f"skip-docs-{DOCUMENT_ID}")
    assert record is not None
    assert record["stage"] == "fetch"
    assert record["last_job_id"] == JOB_ID
    assert record["consecutive_skips"] == 1


def test_an_oversize_record_is_written() -> None:
    records, repository = make_records()

    records.record_oversize(
        job_id=JOB_ID,
        source_id="docs",
        document_id=DOCUMENT_ID,
        external_id="a.txt",
        detected_by=OversizeDetector.CRAWLER,
        size=None,
        retrier=NO_WAIT_RETRIER,
    )

    record = repository.body_of(f"oversize-docs-{DOCUMENT_ID}")
    assert record is not None
    assert (record["detected_by"], record["size"]) == ("crawler", None)


def test_a_store_outage_on_a_write_is_retried_and_then_raised() -> None:
    records, repository = make_records()
    repository.behavior.inject(ops.CREATE, StoreUnavailableError("timeout"), times=2)

    skip(records)  # 3 回目に成功する

    assert repository.body_of(f"skip-docs-{DOCUMENT_ID}") is not None

    other = "b" * 64
    repository.behavior.inject(ops.CREATE, StoreUnavailableError("timeout"), times=None)
    with pytest.raises(StoreUnavailableError):
        skip(records, document_id=other)
    assert len(repository.behavior.calls_of(ops.CREATE)) == 3 + 3


def test_an_unexpected_store_response_is_not_retried() -> None:
    records, repository = make_records()
    repository.behavior.inject(ops.CREATE, StoreUnexpectedResponseError("http_400"), times=None)

    with pytest.raises(StoreUnexpectedResponseError):
        skip(records)

    assert len(repository.behavior.calls_of(ops.CREATE)) == 1


def test_purge_deletes_only_the_selected_records_of_the_given_type() -> None:
    records, repository = make_records()
    keep, drop = "k" * 64, "d" * 64
    skip(records, document_id=keep)
    skip(records, document_id=drop)
    records.record_oversize(
        job_id=JOB_ID,
        source_id="docs",
        document_id=drop,
        external_id="a.txt",
        detected_by=OversizeDetector.INDEXER,
        size=1,
        retrier=NO_WAIT_RETRIER,
    )

    deleted = records.purge(
        source_id="docs",
        record_type=DocumentRecordType.SKIP,
        should_delete=lambda document_id: document_id == drop,
        retrier=NO_WAIT_RETRIER,
    )

    assert deleted == 1
    assert repository.record_ids() == [
        f"oversize-docs-{drop}",
        f"skip-docs-{keep}",
    ]


def test_purge_raises_a_store_write_failure_when_a_partial_failure_persists() -> None:
    records, repository = make_records()
    skip(records)
    repository.fail_bulk_delete_of([f"skip-docs-{DOCUMENT_ID}"], times=None)

    with pytest.raises(StoreWriteFailedError):
        records.purge(
            source_id="docs",
            record_type=DocumentRecordType.SKIP,
            should_delete=lambda _document_id: True,
            retrier=NO_WAIT_RETRIER,
        )


def test_delete_all_of_source_deletes_both_types_and_nothing_of_other_sources() -> None:
    records, repository = make_records()
    skip(records)
    skip(records, source_id="other")
    records.record_oversize(
        job_id=JOB_ID,
        source_id="docs",
        document_id=DOCUMENT_ID,
        external_id="a.txt",
        detected_by=OversizeDetector.CRAWLER,
        size=1,
        retrier=NO_WAIT_RETRIER,
    )
    repository.seed("lock-docs", {"record_type": "lock", "source_id": "docs"})

    deleted = records.delete_all_of_source(source_id="docs", retrier=NO_WAIT_RETRIER)

    assert deleted == 2
    assert repository.record_ids() == ["lock-docs", f"skip-other-{DOCUMENT_ID}"]


def test_job_history_finds_the_previous_completed_crawl() -> None:
    repository = InMemoryRepository()
    previous = "job-20261113T000100Z-00000001"
    repository.seed(
        previous,
        job_fields(previous, registration={"enumerated_count": 7, "partial": False}),
    )

    found = JobHistory(repository).find_previous_completed_crawl(
        source_id="docs",
        excluding_job_id="job-20261113T000500Z-00000009",
        max_jobs=10,
        retrier=NO_WAIT_RETRIER,
    )

    assert found == PreviousCrawl(previous, 7)


def test_job_history_retries_a_store_outage() -> None:
    repository = InMemoryRepository()
    repository.behavior.inject(ops.LIST, StoreUnavailableError("timeout"), times=2)

    found = JobHistory(repository).find_previous_completed_crawl(
        source_id="docs", excluding_job_id="x", max_jobs=10, retrier=NO_WAIT_RETRIER
    )

    assert found is None
    assert len(repository.behavior.calls_of(ops.LIST)) == 3
