"""ジョブ記録の形式と読み書き(版条件つき更新。architecture 3.3.1・5.3)。"""

import pytest

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.infrastructure.opensearch import LIST_MAX_SIZE, StoredRecord
from loreley_crawler.jobs.records import (
    FailureReason,
    JobCreated,
    JobIdCollision,
    JobRecord,
    JobRecordStore,
    JobStatus,
    JobSuperseded,
    JobTrigger,
    JobType,
    JobUpdated,
    new_queued_job_fields,
)
from tests.error_text import logged_text
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW
from tests.fakes.in_memory_repository import InMemoryRepository
from tests.fakes.lost_response_repository import LostResponseRepository
from tests.jobs.records.support import OWNER, job_fields

JOB_ID = "job-20261113T000000Z-00000001"


def create_job(store: JobRecordStore, **overrides: object) -> JobRecord:
    result = store.create(job_fields(JOB_ID, **overrides))
    assert isinstance(result, JobCreated)
    return result.record


# --- 形式 ---


def test_a_queued_job_has_the_fields_of_architecture_3_3_1() -> None:
    fields = new_queued_job_fields(
        job_id=JOB_ID,
        job_type=JobType.SOURCE_DELETE,
        source_id="docs",
        trigger=JobTrigger.SCHEDULE,
        owner=OWNER,
        force_delete=True,
        rewrite_mode=False,
        queued_at=DEFAULT_NOW,
    )

    assert fields == {
        "record_type": "job",
        "job_id": JOB_ID,
        "job_type": "source_delete",
        "source_id": "docs",
        "trigger": "schedule",
        "owner": OWNER,
        "status": "queued",
        "queued_at": "2026-11-13T00:00:00.000Z",
        "force_delete": True,
        "rewrite_mode": False,
    }


def test_the_typed_accessors_read_status_type_and_source() -> None:
    record = JobRecord(JOB_ID, job_fields(JOB_ID), 3, 1)

    assert record.status is JobStatus.QUEUED
    assert record.job_type is JobType.CRAWL
    assert record.source_id == "docs"


@pytest.mark.parametrize("property_name", ["status", "job_type", "source_id"])
def test_a_malformed_field_is_an_unexpected_response_without_the_value(
    property_name: str,
) -> None:
    field = {"status": "status", "job_type": "job_type", "source_id": "source_id"}[property_name]
    fields = job_fields(JOB_ID, **{field: "SECRET-value" if field != "source_id" else 5})
    record = JobRecord(JOB_ID, fields, 3, 1)

    with pytest.raises(StoreUnexpectedResponseError) as raised:
        getattr(record, property_name)

    assert raised.value.error_type == "malformed_job_record"
    assert "SECRET" not in logged_text(raised.value)


def test_the_fields_are_kept_out_of_the_repr() -> None:
    record = JobRecord(JOB_ID, {"warnings": ["SECRET-detail"]}, 3, 1)

    assert "SECRET-detail" not in repr(record)


# --- create・fetch ---


def test_create_saves_the_job_by_its_id_and_returns_the_version() -> None:
    repository = InMemoryRepository()
    store = JobRecordStore(repository)

    record = create_job(store)

    assert repository.body_of(JOB_ID) == job_fields(JOB_ID)
    assert record == JobRecord(JOB_ID, job_fields(JOB_ID), record.seq_no, record.primary_term)
    assert store.fetch(JOB_ID) == record
    assert repository.write_calls() == [ops.CREATE]


def test_fetch_of_a_missing_job_is_none() -> None:
    assert JobRecordStore(InMemoryRepository()).fetch(JOB_ID) is None


@pytest.mark.parametrize(
    ("record_id", "body"),
    [
        ("lock-docs", {"record_type": "lock", "source_id": "docs", "owner": OWNER}),
        ("skip-docs-d1", {"record_type": "skip", "source_id": "docs"}),
        ("oversize-docs-d1", {"record_type": "oversize", "source_id": "docs"}),
        ("maintenance", {"enabled": False}),
    ],
)
def test_only_job_records_are_treated_as_jobs(record_id: str, body: dict[str, object]) -> None:
    repository = InMemoryRepository()
    repository.seed(record_id, body)

    assert JobRecordStore(repository).fetch(record_id) is None


def test_create_does_not_overwrite_a_different_record_with_the_same_id() -> None:
    repository = InMemoryRepository()
    repository.seed(JOB_ID, job_fields(JOB_ID, source_id="another"))

    result = JobRecordStore(repository).create(job_fields(JOB_ID))

    assert result == JobIdCollision()
    assert (repository.body_of(JOB_ID) or {})["source_id"] == "another"


def test_create_whose_first_write_succeeded_but_lost_its_response_succeeds_on_retry() -> None:
    repository = LostResponseRepository()
    repository.lose_response_of(ops.CREATE)
    store = JobRecordStore(repository)

    with pytest.raises(StoreUnavailableError):
        store.create(job_fields(JOB_ID))  # 呼び出し側がリトライする
    result = store.create(job_fields(JOB_ID))

    assert isinstance(result, JobCreated)
    assert repository.body_of(JOB_ID) == job_fields(JOB_ID)


def test_a_retried_create_is_not_a_success_once_the_job_has_changed() -> None:
    repository = InMemoryRepository()
    store = JobRecordStore(repository)
    record = create_job(store)
    store.update(record, {"status": "running"})

    # 内容が変わっている = 自分の `create` の直後の状態ではない(別のジョブとの衝突として扱う)。
    assert store.create(job_fields(JOB_ID)) == JobIdCollision()


# --- update ---


def test_update_overlays_the_changes_conditioned_on_the_read_version() -> None:
    repository = InMemoryRepository()
    store = JobRecordStore(repository)
    record = create_job(store)

    result = store.update(record, {"status": "running", "started_at": "2026-11-13T00:01:00.000Z"})

    assert isinstance(result, JobUpdated)
    assert result.record.status is JobStatus.RUNNING
    assert result.record.seq_no > record.seq_no
    assert repository.body_of(JOB_ID) == {
        **job_fields(JOB_ID),
        "status": "running",
        "started_at": "2026-11-13T00:01:00.000Z",
    }
    assert store.fetch(JOB_ID) == result.record
    assert repository.write_calls() == [ops.CREATE, ops.REPLACE]


def test_updates_chain_on_the_version_returned_by_the_previous_update() -> None:
    store = JobRecordStore(InMemoryRepository())
    record = create_job(store)

    first = store.update(record, {"status": "running"})
    assert isinstance(first, JobUpdated)
    second = store.update(first.record, {"registration": {"partial": True}})

    assert isinstance(second, JobUpdated)
    assert second.record.fields["status"] == "running"
    assert second.record.fields["registration"] == {"partial": True}


def test_a_stale_version_never_overwrites_a_newer_record() -> None:
    repository = InMemoryRepository()
    store = JobRecordStore(repository)
    record = create_job(store)
    # 管理者のロック解放が、リース切れの `running` を `failed` にした。
    repository.seed(
        JOB_ID, {**job_fields(JOB_ID), "status": "failed", "failure_reason": "lock_released"}
    )

    result = store.update(record, {"status": "running", "registration": {"partial": True}})

    assert isinstance(result, JobSuperseded)
    assert result.current is not None
    assert result.current.status is JobStatus.FAILED
    assert (repository.body_of(JOB_ID) or {})["failure_reason"] == "lock_released"
    assert "registration" not in (repository.body_of(JOB_ID) or {})


def test_update_of_a_vanished_job_is_superseded_with_no_current_record() -> None:
    repository = InMemoryRepository()
    store = JobRecordStore(repository)
    record = create_job(store)
    repository.delete_ids([JOB_ID])

    assert store.update(record, {"status": "running"}) == JobSuperseded(None)


def test_update_whose_first_write_succeeded_but_lost_its_response_succeeds_on_retry() -> None:
    repository = LostResponseRepository()
    store = JobRecordStore(repository)
    record = create_job(store)
    repository.lose_response_of(ops.REPLACE)

    with pytest.raises(StoreUnavailableError):
        store.update(record, {"status": "running"})
    retried = store.update(record, {"status": "running"})  # 古い版のままリトライ

    assert isinstance(retried, JobUpdated)
    assert retried.record.status is JobStatus.RUNNING
    assert repository.write_calls() == [ops.CREATE, ops.REPLACE, ops.REPLACE]


def test_a_retried_update_is_superseded_when_someone_wrote_after_the_first_write() -> None:
    repository = LostResponseRepository()
    store = JobRecordStore(repository)
    record = create_job(store)
    repository.lose_response_of(ops.REPLACE)
    with pytest.raises(StoreUnavailableError):
        store.update(record, {"status": "running"})
    repository.seed(JOB_ID, {**job_fields(JOB_ID), "status": "failed"})

    result = store.update(record, {"status": "running"})

    assert isinstance(result, JobSuperseded)
    assert result.current is not None
    assert result.current.status is JobStatus.FAILED


def test_update_does_not_change_the_record_it_was_given() -> None:
    store = JobRecordStore(InMemoryRepository())
    record = create_job(store)

    store.update(record, {"status": "running"})

    assert record.fields["status"] == "queued"


def test_fetching_an_empty_job_id_is_no_job_and_never_reaches_the_store() -> None:
    repository = InMemoryRepository()

    assert JobRecordStore(repository).fetch("") is None
    assert repository.behavior.calls_of(ops.FETCH) == []


# --- 一覧(Job Runner の取り出し・起動時の回復) ---


def seed_job(
    repository: InMemoryRepository, job_id: str, *, status: str = "queued", **overrides: object
) -> None:
    repository.seed(job_id, job_fields(job_id, status=status, **overrides))


def test_the_oldest_queued_job_of_the_owner_is_found_first() -> None:
    repository = InMemoryRepository()
    # `job_id` の辞書順と `queued_at` の順が逆になるようにする。
    seed_job(repository, "job-y", queued_at="2026-11-13T00:00:02.000Z")
    seed_job(repository, "job-z", queued_at="2026-11-13T00:00:01.000Z")
    seed_job(repository, "job-x", queued_at="2026-11-13T00:00:03.000Z")

    found = JobRecordStore(repository).find_oldest_queued(OWNER)

    assert found is not None
    assert found.job_id == "job-z"


def test_queued_jobs_queued_at_the_same_instant_are_ordered_by_job_id() -> None:
    repository = InMemoryRepository()
    seed_job(repository, "job-2")
    seed_job(repository, "job-1")

    found = JobRecordStore(repository).find_oldest_queued(OWNER)

    assert found is not None
    assert found.job_id == "job-1"


def test_the_queue_ignores_other_owners_other_statuses_and_other_record_types() -> None:
    repository = InMemoryRepository()
    seed_job(repository, "job-other-owner", owner="crawler-2")
    seed_job(repository, "job-running", status="running")
    seed_job(repository, "job-done", status="succeeded")
    repository.seed("lock-docs", {"record_type": "lock", "status": "queued", "owner": OWNER})

    assert JobRecordStore(repository).find_oldest_queued(OWNER) is None


def test_running_jobs_of_the_owner_are_listed() -> None:
    repository = InMemoryRepository()
    seed_job(repository, "job-2", status="running", queued_at="2026-11-13T00:00:02.000Z")
    seed_job(repository, "job-1", status="running", queued_at="2026-11-13T00:00:01.000Z")
    seed_job(repository, "job-other", status="running", owner="crawler-2")
    seed_job(repository, "job-queued")

    running = JobRecordStore(repository).list_running(OWNER)

    assert [record.job_id for record in running] == ["job-1", "job-2"]


def test_a_truncated_running_list_is_not_returned_as_a_success() -> None:
    repository = InMemoryRepository()
    full_page = [
        StoredRecord(f"job-{i}", job_fields(f"job-{i}", status="running"), i, 1)
        for i in range(LIST_MAX_SIZE)
    ]
    repository.behavior.inject(ops.LIST, full_page)

    with pytest.raises(StoreUnexpectedResponseError) as raised:
        JobRecordStore(repository).list_running(OWNER)

    assert raised.value.error_type == "job_list_truncated"


def test_terminal_statuses_are_the_four_final_states() -> None:
    assert {status for status in JobStatus if status.is_terminal} == {
        JobStatus.SUCCEEDED,
        JobStatus.PARTIALLY_SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }


def test_the_failure_reasons_are_the_codes_of_architecture_4_8() -> None:
    assert {reason.value for reason in FailureReason} == {
        "config_invalid",
        "enumeration_failed",
        "indexer_unavailable",
        "indexer_rejected",
        "external_id_collision",
        "enumeration_too_large",
        "skip_limit_exceeded",
        "conflict_unresolved",
        "lock_lost",
        "document_id_mismatch",
        "maintenance",
        "finish_notice_failed",
        "internal_error",
        "store_unavailable",
        "crawler_restart",
        "lock_released",
    }
