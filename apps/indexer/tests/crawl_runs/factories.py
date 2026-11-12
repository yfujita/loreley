"""`loreley-deletions` の記録のテスト用ファクトリ。"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from loreley_indexer.crawl_runs import FinishNotification, StartNotification
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionRecord,
    DeletionResultRecord,
    DeletionStatus,
    FinishOutcome,
    deletion_record_id,
    deletion_result_record_id,
)
from tests.fakes.in_memory_store import InMemoryStore

SOURCE_ID = "src-docs"
CRAWL_ID = "job-20261109-0001"
CRAWL_STARTED_AT = datetime(2026, 11, 9, 1, 0, 0, tzinfo=UTC)
CRAWL_STARTED_AT_TEXT = "2026-11-09T01:00:00.000Z"  # 保存される形式(UTC・ミリ秒)


def make_result(**overrides: Any) -> DeletionResultRecord:
    """開始通知を受理した直後(`running`、終了通知なし)の削除結果。"""
    base = DeletionResultRecord(
        crawl_id=CRAWL_ID,
        source_id=SOURCE_ID,
        status=DeletionStatus.RUNNING,
        started_at=CRAWL_STARTED_AT,
        crawl_started_at=CRAWL_STARTED_AT,
        ttl=86_400,
        ratio_threshold=0.2,
        min_delete_count=10,
        forced=False,
        rewrite_mode=False,
    )
    return replace(base, **overrides)


def make_generation(**overrides: Any) -> DeletionRecord:
    base = DeletionRecord(
        source_id=SOURCE_ID,
        crawl_id=CRAWL_ID,
        crawl_started_at=CRAWL_STARTED_AT,
        ttl=86_400,
        ratio_threshold=0.2,
        min_delete_count=10,
        force_delete=False,
        updated_at=CRAWL_STARTED_AT,
    )
    return replace(base, **overrides)


def seed_result(store: InMemoryStore, result: DeletionResultRecord) -> None:
    store.seed(deletion_result_record_id(result.crawl_id), result.to_body())


MALFORMED_VALUE = "sentinel-malformed-value"


def seed_malformed_result(store: InMemoryStore, **overrides: Any) -> str:
    """形式が不正な(`ttl` が数値でない)削除結果を置く。記録の ID を返す。

    `from_body` が `MalformedRecordError` を投げる。不正な値(`MALFORMED_VALUE`)がログや
    例外に出ないことの確認に使う。
    """
    record = make_result(**overrides)
    record_id = deletion_result_record_id(record.crawl_id)
    store.seed(record_id, {**record.to_body(), "ttl": MALFORMED_VALUE})
    return record_id


def make_start(**overrides: Any) -> StartNotification:
    """開始通知。既定は `make_result()` と同じ複写値になる。"""
    base = StartNotification(
        crawl_id=CRAWL_ID,
        source_id=SOURCE_ID,
        crawl_started_at=CRAWL_STARTED_AT,
        ttl=86_400,
        ratio_threshold=0.2,
        min_delete_count=10,
        force_delete=False,
        rewrite_mode=False,
    )
    return replace(base, **overrides)


def hex_id(number: int) -> str:
    """64 桁小文字 16 進の文書 ID(`number` で一意)。"""
    return f"{number:064x}"


def make_finish(**overrides: Any) -> FinishNotification:
    """`enumeration_completed` の終了通知(スキップ 2 件、サイズ超過なし)。"""
    base = FinishNotification(
        crawl_id=CRAWL_ID,
        source_id=SOURCE_ID,
        outcome=FinishOutcome.ENUMERATION_COMPLETED,
        finished_at=CRAWL_STARTED_AT + timedelta(minutes=12),
        enumerated_count=1203,
        skipped_document_ids=(hex_id(2), hex_id(1)),
        oversize_document_ids=(),
    )
    return replace(base, **overrides)


def make_failed_finish(
    outcome: FinishOutcome = FinishOutcome.FAILED, **overrides: Any
) -> FinishNotification:
    """`failed`・`cancelled` の終了通知(既定では件数と ID 一覧を省略する)。"""
    omitted: dict[str, Any] = {
        "enumerated_count": None,
        "skipped_document_ids": None,
        "oversize_document_ids": None,
    }
    return make_finish(outcome=outcome, **{**omitted, **overrides})


def stored_result(store: InMemoryStore, crawl_id: str = CRAWL_ID) -> DeletionResultRecord:
    """保存されている削除結果(なければテストの失敗)。"""
    body = store.body_of(deletion_result_record_id(crawl_id))
    assert body is not None, "the deletion result is not stored"
    return DeletionResultRecord.from_body(body)


def stored_generation(store: InMemoryStore, source_id: str = SOURCE_ID) -> DeletionRecord:
    body = store.body_of(deletion_record_id(source_id))
    assert body is not None, "the generation record is not stored"
    return DeletionRecord.from_body(body)


def snapshot(store: InMemoryStore) -> dict[str, dict[str, Any] | None]:
    """全記録の ID → 保存内容。「状態が変わらない」を、内容の同一性で確かめるのに使う。"""
    return {record_id: store.body_of(record_id) for record_id in store.record_ids()}
