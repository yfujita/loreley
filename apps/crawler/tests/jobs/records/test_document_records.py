"""スキップ記録・原本サイズ超過記録の書き込み(architecture 3.3.3・3.3.4・6.4・6.5)。"""

from datetime import timedelta

import pytest

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.infrastructure.opensearch import AlreadyExists
from loreley_crawler.jobs.records import (
    DocumentRecordStore,
    OversizeDetector,
    SkipStage,
    document_record_id,
)
from loreley_crawler.jobs.records.document_records import DocumentRecordType
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.in_memory_repository import InMemoryRepository
from tests.fakes.lost_response_repository import LostResponseRepository

D1 = "a" * 64
NOW = "2026-11-13T00:00:00.000Z"


def record_skip(
    store: DocumentRecordStore,
    job_id: str = "job-1",
    *,
    stage: SkipStage = SkipStage.FETCH,
    reason: str = "fetch_permission_denied",
    attempts: int = 1,
) -> None:
    store.record_skip(
        job_id=job_id,
        source_id="docs",
        document_id=D1,
        external_id="a/b.txt",
        stage=stage,
        reason=reason,
        attempts=attempts,
    )


def record_oversize(
    store: DocumentRecordStore, job_id: str = "job-1", *, size: int | None = 100
) -> None:
    store.record_oversize(
        job_id=job_id,
        source_id="docs",
        document_id=D1,
        external_id="a/b.txt",
        detected_by=OversizeDetector.CRAWLER,
        size=size,
    )


def test_record_ids_follow_architecture_3_3() -> None:
    assert document_record_id(DocumentRecordType.SKIP, "docs", D1) == f"skip-docs-{D1}"
    assert document_record_id(DocumentRecordType.OVERSIZE, "docs", D1) == f"oversize-docs-{D1}"


# --- スキップ記録 ---


def test_the_first_skip_creates_a_record_with_the_fields_of_architecture_3_3_3(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()

    record_skip(DocumentRecordStore(repository, clock), attempts=3)

    assert repository.body_of(f"skip-docs-{D1}") == {
        "record_type": "skip",
        "source_id": "docs",
        "document_id": D1,
        "external_id": "a/b.txt",
        "stage": "fetch",
        "reason": "fetch_permission_denied",
        "attempts": 3,
        "consecutive_skips": 1,
        "first_skipped_at": NOW,
        "last_skipped_at": NOW,
        "last_job_id": "job-1",
    }
    assert repository.write_calls() == [ops.CREATE]


def test_a_skip_in_a_later_job_updates_the_record_and_counts_one_more_skip(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    store = DocumentRecordStore(repository, clock)
    record_skip(store, "job-1", attempts=3)
    clock.advance(seconds=3600)

    record_skip(store, "job-2", stage=SkipStage.INDEX, reason="document_rejected", attempts=2)

    assert repository.body_of(f"skip-docs-{D1}") == {
        "record_type": "skip",
        "source_id": "docs",
        "document_id": D1,
        "external_id": "a/b.txt",
        "stage": "index",
        "reason": "document_rejected",
        "attempts": 2,
        "consecutive_skips": 2,
        "first_skipped_at": NOW,  # 最初の日時は保つ
        "last_skipped_at": "2026-11-13T01:00:00.000Z",
        "last_job_id": "job-2",
    }
    assert repository.write_calls() == [ops.CREATE, ops.REPLACE]


def test_skipping_the_same_document_again_in_the_same_job_does_not_count_twice(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    store = DocumentRecordStore(repository, clock)
    record_skip(store, "job-1")
    clock.advance(seconds=60)

    record_skip(store, "job-1")

    assert (repository.body_of(f"skip-docs-{D1}") or {})["consecutive_skips"] == 1
    assert repository.write_calls() == [ops.CREATE]


def test_a_lost_create_response_does_not_double_count_on_the_retry(clock: FixedClock) -> None:
    repository = LostResponseRepository()
    repository.lose_response_of(ops.CREATE)
    store = DocumentRecordStore(repository, clock)

    with pytest.raises(StoreUnavailableError):
        record_skip(store)
    record_skip(store)  # 呼び出し側のリトライ

    assert (repository.body_of(f"skip-docs-{D1}") or {})["consecutive_skips"] == 1


def test_a_lost_replace_response_does_not_double_count_on_the_retry(clock: FixedClock) -> None:
    repository = LostResponseRepository()
    store = DocumentRecordStore(repository, clock)
    record_skip(store, "job-1")
    repository.lose_response_of(ops.REPLACE)

    with pytest.raises(StoreUnavailableError):
        record_skip(store, "job-2")
    record_skip(store, "job-2")

    assert (repository.body_of(f"skip-docs-{D1}") or {})["consecutive_skips"] == 2


def test_a_version_conflict_is_reread_and_the_skip_is_added_to_the_newer_record(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    store = DocumentRecordStore(repository, clock)
    record_skip(store, "job-1")
    record_id = f"skip-docs-{D1}"
    newer = {**(repository.body_of(record_id) or {}), "consecutive_skips": 5}
    repository.behavior.before(ops.REPLACE, lambda: repository.seed(record_id, newer))

    record_skip(store, "job-2")

    assert (repository.body_of(record_id) or {})["consecutive_skips"] == 6
    assert repository.write_calls() == [ops.CREATE, ops.REPLACE, ops.REPLACE]  # 競合 → 成功


def test_a_create_conflict_is_reread_and_updated(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = DocumentRecordStore(repository, clock)
    record_skip(store, "job-1")
    # 読んだ時点では記録がなく(別の書き手が直後に作った状況)、`create` が `AlreadyExists` になる。
    repository.behavior.inject(ops.FETCH, None)
    repository.behavior.inject(ops.CREATE, AlreadyExists())

    record_skip(store, "job-2")

    assert (repository.body_of(f"skip-docs-{D1}") or {})["consecutive_skips"] == 2


def test_a_write_that_keeps_conflicting_becomes_a_store_failure(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = DocumentRecordStore(repository, clock)
    record_skip(store, "job-1")
    record_id = f"skip-docs-{D1}"
    for _ in range(3):
        repository.behavior.before(
            ops.REPLACE,
            lambda: repository.seed(record_id, repository.body_of(record_id) or {}),
        )

    with pytest.raises(StoreUnavailableError) as raised:
        record_skip(store, "job-2")

    assert raised.value.reason == "document_record_write_contention"


def test_a_corrupt_consecutive_skips_count_restarts_from_one(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    record_id = f"skip-docs-{D1}"
    repository.seed(
        record_id, {"record_type": "skip", "consecutive_skips": "x", "last_job_id": "job-0"}
    )

    record_skip(DocumentRecordStore(repository, clock), "job-1")

    assert (repository.body_of(record_id) or {})["consecutive_skips"] == 1


# --- 原本サイズ超過記録 ---


def test_the_first_oversize_creates_a_record_with_the_fields_of_architecture_3_3_4(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()

    record_oversize(DocumentRecordStore(repository, clock), size=21_000_000)

    assert repository.body_of(f"oversize-docs-{D1}") == {
        "record_type": "oversize",
        "source_id": "docs",
        "document_id": D1,
        "external_id": "a/b.txt",
        "detected_by": "crawler",
        "size": 21_000_000,
        "first_detected_at": NOW,
        "last_detected_at": NOW,
        "last_job_id": "job-1",
    }


def test_the_size_may_be_unknown(clock: FixedClock) -> None:
    repository = InMemoryRepository()

    record_oversize(DocumentRecordStore(repository, clock), size=None)

    assert (repository.body_of(f"oversize-docs-{D1}") or {})["size"] is None


def test_a_later_oversize_updates_the_detection_and_keeps_the_first_time(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    store = DocumentRecordStore(repository, clock)
    record_oversize(store, "job-1", size=100)
    clock.set(DEFAULT_NOW + timedelta(days=1))

    store.record_oversize(
        job_id="job-2",
        source_id="docs",
        document_id=D1,
        external_id="a/b.txt",
        detected_by=OversizeDetector.INDEXER,
        size=200,
    )

    body = repository.body_of(f"oversize-docs-{D1}") or {}
    assert body["detected_by"] == "indexer"
    assert body["size"] == 200
    assert body["first_detected_at"] == NOW
    assert body["last_detected_at"] == "2026-11-14T00:00:00.000Z"
    assert body["last_job_id"] == "job-2"


def test_the_same_job_recording_oversize_again_changes_nothing(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = DocumentRecordStore(repository, clock)
    record_oversize(store, "job-1")

    record_oversize(store, "job-1", size=999)

    assert (repository.body_of(f"oversize-docs-{D1}") or {})["size"] == 100


def test_skip_and_oversize_records_of_the_same_document_coexist(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = DocumentRecordStore(repository, clock)

    record_skip(store)
    record_oversize(store)

    assert repository.record_ids() == [f"oversize-docs-{D1}", f"skip-docs-{D1}"]
