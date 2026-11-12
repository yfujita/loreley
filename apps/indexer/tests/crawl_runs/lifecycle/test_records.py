from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionRecord,
    DeletionResultRecord,
    DeletionStatus,
    FinishOutcome,
    MalformedRecordError,
    deletion_record_id,
    deletion_result_record_id,
)
from tests.crawl_runs.factories import (
    CRAWL_ID,
    CRAWL_STARTED_AT,
    CRAWL_STARTED_AT_TEXT,
    SOURCE_ID,
    make_generation,
    make_result,
)
from tests.fakes.in_memory_store import InMemoryStore

FINISHED_AT = datetime(2026, 11, 9, 2, 30, 15, 123000, tzinfo=UTC)


def full_result() -> DeletionResultRecord:
    return make_result(
        status=DeletionStatus.FAILED,
        reason=DeletionReason.DELETE_ERROR,
        reason_detail="http_503",
        outcome=FinishOutcome.ENUMERATION_COMPLETED,
        ended_at=FINISHED_AT,
        finish_received_at=FINISHED_AT,
        finish_request_digest="d" * 64,
        enumerated_count=120,
        skipped_document_ids=("a" * 64, "b" * 64),
        oversize_document_ids=(),
        skip_and_oversize_id_count=2,
        skip_and_oversize_id_limit_exceeded=False,
        deletion_started_at=FINISHED_AT,
        n_seen=118,
        e_missing=2,
        target_count=5,
        denominator=118,
        deleted_count=3,
        forced=True,
        rewrite_mode=True,
    )


# --- 記録 ID ---


def test_record_ids_follow_the_design() -> None:
    assert deletion_record_id("src-docs") == "deletion-src-docs"
    assert deletion_result_record_id("job-1") == "deletion_result-job-1"


# --- 状態 ---


def test_only_running_is_not_terminal() -> None:
    assert {status for status in DeletionStatus if not status.is_terminal} == {
        DeletionStatus.RUNNING
    }


# --- 直列化の往復 ---


def test_minimal_result_round_trips() -> None:
    record = make_result()
    assert DeletionResultRecord.from_body(record.to_body()) == record


def test_full_result_round_trips() -> None:
    record = full_result()
    assert DeletionResultRecord.from_body(record.to_body()) == record


def test_generation_record_round_trips() -> None:
    record = make_generation()
    assert DeletionRecord.from_body(record.to_body()) == record


def test_results_round_trip_through_the_store() -> None:
    store = InMemoryStore()
    record = full_result()
    store.save(deletion_result_record_id(record.crawl_id), record.to_body())
    stored = store.fetch(deletion_result_record_id(record.crawl_id))
    assert stored is not None
    assert DeletionResultRecord.from_body(stored.source) == record


def test_body_uses_the_design_field_names_and_normalized_timestamps() -> None:
    body = make_result(
        finish_received_at=datetime(2026, 11, 9, 10, 0, 0, tzinfo=UTC),
        reason=DeletionReason.SUPERSEDED,
        status=DeletionStatus.DISCARDED,
    ).to_body()
    assert body["record_type"] == "deletion_result"
    assert body["source_id"] == SOURCE_ID
    assert body["crawl_id"] == CRAWL_ID
    assert body["status"] == "discarded"
    assert body["reason"] == "superseded"
    assert body["crawl_started_at"] == CRAWL_STARTED_AT_TEXT
    assert body["finish_received_at"] == "2026-11-09T10:00:00.000Z"
    assert body["forced"] is False
    assert body["rewrite_mode"] is False  # 省略は false に正規化して保存する(K37)


def test_generation_body_has_its_own_record_type() -> None:
    body = make_generation().to_body()
    assert body["record_type"] == "deletion"
    assert body["force_delete"] is False


def test_fields_without_a_value_are_not_stored() -> None:
    body = make_result().to_body()
    for name in (
        "reason",
        "outcome",
        "finish_received_at",
        "finish_request_digest",
        "skipped_document_ids",
        "oversize_document_ids",
        "deleted_count",
    ):
        assert name not in body


def test_empty_id_list_is_kept_distinct_from_no_id_list() -> None:
    empty = make_result(skipped_document_ids=())
    absent = make_result()
    assert empty.to_body()["skipped_document_ids"] == []
    assert DeletionResultRecord.from_body(empty.to_body()).skipped_document_ids == ()
    assert DeletionResultRecord.from_body(absent.to_body()).skipped_document_ids is None


def test_clearing_the_id_lists_removes_them_but_keeps_the_digest() -> None:
    # 終端状態への遷移と同じ書き込みで ID 一覧を消し、ダイジェストは残す(K35)。
    store = InMemoryStore()
    record = full_result()
    store.save(deletion_result_record_id(CRAWL_ID), record.to_body())
    cleared = replace(record, skipped_document_ids=None, oversize_document_ids=None)
    store.save(deletion_result_record_id(CRAWL_ID), cleared.to_body())
    body = store.body_of(deletion_result_record_id(CRAWL_ID))
    assert body is not None
    assert "skipped_document_ids" not in body
    assert "oversize_document_ids" not in body
    assert body["finish_request_digest"] == "d" * 64


def test_ratio_threshold_accepts_an_integer_stored_value() -> None:
    body = make_result().to_body() | {"ratio_threshold": 1}
    assert DeletionResultRecord.from_body(body).ratio_threshold == 1.0


def test_timestamps_with_other_notations_are_read_as_the_same_instant() -> None:
    body = make_result().to_body() | {"crawl_started_at": "2026-11-09T10:00:00+09:00"}
    assert DeletionResultRecord.from_body(body).crawl_started_at == CRAWL_STARTED_AT


# --- 不正な記録 ---


def corrupted(**overrides: Any) -> dict[str, Any]:
    return make_result().to_body() | overrides


def without(name: str) -> dict[str, Any]:
    body = make_result().to_body()
    del body[name]
    return body


@pytest.mark.parametrize(
    ("body", "field_name"),
    [
        (corrupted(record_type="deletion"), "record_type"),
        (without("record_type"), "record_type"),
        (without("source_id"), "source_id"),
        (without("status"), "status"),
        (corrupted(status="paused"), "status"),
        (corrupted(reason="unknown_reason"), "reason"),
        (corrupted(outcome="done"), "outcome"),
        (corrupted(ttl="86400"), "ttl"),
        (corrupted(ttl=True), "ttl"),  # bool は数値として受け付けない
        (corrupted(ratio_threshold="0.2"), "ratio_threshold"),
        (corrupted(forced="false"), "forced"),
        (corrupted(rewrite_mode=None), "rewrite_mode"),
        (corrupted(crawl_started_at="yesterday"), "crawl_started_at"),
        (corrupted(crawl_started_at="2026-11-09T01:00:00"), "crawl_started_at"),  # オフセットなし
        (corrupted(skipped_document_ids="abc"), "skipped_document_ids"),
        (corrupted(skipped_document_ids=["a", 1]), "skipped_document_ids"),
        (corrupted(deleted_count=1.5), "deleted_count"),
    ],
)
def test_malformed_result_names_the_field(body: dict[str, Any], field_name: str) -> None:
    with pytest.raises(MalformedRecordError) as exc_info:
        DeletionResultRecord.from_body(body)
    assert exc_info.value.field_name == field_name


def test_malformed_record_error_does_not_echo_the_stored_value() -> None:
    sentinel = "SECRET-SENTINEL"
    with pytest.raises(MalformedRecordError) as exc_info:
        DeletionResultRecord.from_body(corrupted(status=sentinel, source_id=sentinel))
    assert sentinel not in str(exc_info.value)


def test_generation_record_rejects_a_result_body() -> None:
    with pytest.raises(MalformedRecordError):
        DeletionRecord.from_body(make_result().to_body())
