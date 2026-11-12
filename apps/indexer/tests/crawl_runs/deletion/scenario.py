"""削除のテスト用の場面づくり。

時刻の関係(固定時計 `DEFAULT_NOW` = 2026-11-11T00:00Z、TTL 3 日で `cutoff` = 11-08T00:00Z):
- 見つかった文書: `last_seen_at` が `crawl_started_at`(11-09T01:00Z)。`N_seen` に数えられ、
  対象にならない
- 期限切れの文書: `cutoff` より前。削除の対象
- TTL 内で見つからなかった文書: `crawl_started_at` より前で `cutoff` 以後。`D` には
  数えられるが、対象でも `N_seen` でもない
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from loreley_indexer.common.timestamps import format_instant
from loreley_indexer.crawl_runs import DeletionManager, DeletionOutcome
from loreley_indexer.crawl_runs.lifecycle import DeletionResultRecord, FinishOutcome
from loreley_indexer.infrastructure.opensearch import OpenSearchUnavailableError
from tests.crawl_runs.factories import (
    CRAWL_ID,
    CRAWL_STARTED_AT,
    SOURCE_ID,
    hex_id,
    make_result,
    seed_result,
)
from tests.documents.factories import set_maintenance, set_malformed_maintenance
from tests.fakes import in_memory_store as store_ops
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore

OTHER_SOURCE_ID = "other-source"
TTL_SECONDS = 3 * 24 * 60 * 60
SEEN_AT = CRAWL_STARTED_AT
EXPIRED_AT = CRAWL_STARTED_AT - timedelta(days=5)
WITHIN_TTL_AT = CRAWL_STARTED_AT - timedelta(hours=1)
FINISH_RECEIVED_AT = datetime(2026, 11, 9, 2, 0, 0, tzinfo=UTC)

# 文書 ID の範囲(カテゴリごとに分ける。昇順は ID の大小で決まる)。
SEEN_BASE = 1_000
EXPIRED_BASE = 2_000
WITHIN_TTL_BASE = 3_000
NEW_BASE = 5_000  # 検索インデックスにない文書(スキップした新規文書など)
STALE_BASE = 7_000  # 期限切れだが、スキップ文書・サイズ超過文書の一覧に載っている文書


def received_at(minutes: int) -> datetime:
    """終了通知の受理時刻(`FINISH_RECEIVED_AT` から `minutes` 分後)。"""
    return FINISH_RECEIVED_AT + timedelta(minutes=minutes)


def process(manager: DeletionManager, crawl_id: str = CRAWL_ID) -> DeletionOutcome:
    return manager.processor.process(crawl_id)


def remaining(search_index: InMemorySearchIndex, document_ids: tuple[str, ...]) -> set[str]:
    """`document_ids` のうち、検索インデックスに残っている ID。"""
    present = set(search_index.document_ids())
    return {document_id for document_id in document_ids if document_id in present}


def ids(base: int, count: int) -> tuple[str, ...]:
    return tuple(hex_id(base + number) for number in range(count))


def document_source(source_id: str, last_seen_at: datetime, **extra: Any) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "last_seen_at": format_instant(last_seen_at),
        "title": "title",
        **extra,
    }


def seed_documents(
    search_index: InMemorySearchIndex,
    document_ids: tuple[str, ...],
    *,
    last_seen_at: datetime,
    source_id: str = SOURCE_ID,
    searchable: bool = True,
    **extra: Any,
) -> None:
    for document_id in document_ids:
        search_index.seed(
            document_id, document_source(source_id, last_seen_at, **extra), searchable=searchable
        )


def queued_result(
    crawl_id: str = CRAWL_ID,
    *,
    enumerated_count: int,
    finish_received_at: datetime = FINISH_RECEIVED_AT,
    skipped: tuple[str, ...] | None = (),
    oversize: tuple[str, ...] | None = (),
    **overrides: Any,
) -> DeletionResultRecord:
    """終了通知(`enumeration_completed`)を受理した直後(待機中・判定前)の削除結果。"""
    fields: dict[str, Any] = {
        "ttl": TTL_SECONDS,
        "finish_received_at": finish_received_at,
        "finish_request_digest": "d" * 64,
        "outcome": FinishOutcome.ENUMERATION_COMPLETED,
        "enumerated_count": enumerated_count,
        "skipped_document_ids": skipped,
        "oversize_document_ids": oversize,
        "skip_and_oversize_id_count": len(skipped or ()) + len(oversize or ()),
        "skip_and_oversize_id_limit_exceeded": False,
    }
    return make_result(crawl_id=crawl_id, **{**fields, **overrides})


@dataclass(frozen=True)
class Scenario:
    result: DeletionResultRecord
    seen: tuple[str, ...]
    expired: tuple[str, ...]
    within_ttl: tuple[str, ...]
    others: tuple[str, ...] = field(default=())

    @property
    def crawl_id(self) -> str:
        return self.result.crawl_id


def seed_scenario(
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    *,
    seen: int = 0,
    expired: int = 0,
    within_ttl: int = 0,
    other_source_expired: int = 0,
    other_source_seen: int = 0,
    crawl_id: str = CRAWL_ID,
    **result_overrides: Any,
) -> Scenario:
    """文書と、待機中の削除結果を置く。`enumerated_count` の既定は `seen`(件数照合が成立)。"""
    seen_ids = ids(SEEN_BASE, seen)
    expired_ids = ids(EXPIRED_BASE, expired)
    within_ttl_ids = ids(WITHIN_TTL_BASE, within_ttl)
    # 別ソースの文書(期限切れ・見つかった)。分母 D・`N_seen`・対象に混ざらないことの確認に使う。
    other_ids = ids(9_000, other_source_expired) + ids(9_500, other_source_seen)
    seed_documents(search_index, seen_ids, last_seen_at=SEEN_AT)
    seed_documents(search_index, expired_ids, last_seen_at=EXPIRED_AT)
    seed_documents(search_index, within_ttl_ids, last_seen_at=WITHIN_TTL_AT)
    seed_documents(
        search_index,
        ids(9_000, other_source_expired),
        last_seen_at=EXPIRED_AT,
        source_id=OTHER_SOURCE_ID,
    )
    seed_documents(
        search_index,
        ids(9_500, other_source_seen),
        last_seen_at=SEEN_AT,
        source_id=OTHER_SOURCE_ID,
    )
    result = queued_result(crawl_id, **{"enumerated_count": seen, **result_overrides})
    seed_result(deletions_store, result)
    return Scenario(result, seen_ids, expired_ids, within_ttl_ids, other_ids)


def fail_the_maintenance_check_at(jobs_store: InMemoryStore, nth_check: int) -> None:
    """`nth_check` 回目(1 始まり)のメンテナンスフラグの確認を、OpenSearch の障害で失敗させる。"""
    for _ in range(nth_check - 1):
        jobs_store.behavior.before(store_ops.FETCH, lambda: None, key="maintenance")

    def fail() -> None:
        raise OpenSearchUnavailableError("http_503")

    jobs_store.behavior.before(store_ops.FETCH, fail, key="maintenance")


def raise_the_maintenance_flag_at_check(
    jobs_store: InMemoryStore, nth_check: int, *, body: dict[str, Any] | None = None
) -> None:
    """`nth_check` 回目(1 始まり)のメンテナンスフラグの確認の直前に、フラグを立てる。

    確認は、判定の前に 1 回、その後はバッチごとに 1 回。`body` を渡すと、その内容の文書を置く
    (不正な形式を含む。省略時は `enabled: True`)。
    """
    for _ in range(nth_check - 1):
        jobs_store.behavior.before(store_ops.FETCH, lambda: None, key="maintenance")
    if body is None:
        raise_flag = lambda: set_maintenance(jobs_store, enabled=True)  # noqa: E731
    else:
        raise_flag = lambda: set_malformed_maintenance(jobs_store, body)  # noqa: E731
    jobs_store.behavior.before(store_ops.FETCH, raise_flag, key="maintenance")
