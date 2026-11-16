"""スキップ記録・原本サイズ超過記録の整理と一括削除(architecture 3.1・6.4・8.1 の順 3。CM-P-24)。

全件走査(PIT + `search_after`)で対象の ID を集め、ID のバルク削除で消す。10,000 件を超えても
取りこぼさない。

- **`record_type` ごとに 1 回ずつ走査する**: `sort` は `document_id`(1 ソース・1 種類の中で
  一意)で終える。`skip` と `oversize` を 1 回の走査にまとめると、同じ `document_id` が共存した
  ときに同順位が生じ、`search_after` がページ境界で取りこぼす(`scan` は境界の同値を検出
  できない。0007 §4-1)。
- **走査全体をリトライの単位にする**: `StoreUnavailableError("pit_expired")` は、走査が終了して
  いるので、個々の呼び出しのリトライでは直らない。`with scan(...)` ブロック全体をやり直す
  (削除はしていない段階なので、やり直しても結果は同じ)。
- 走査で ID を集め切ってから削除する(PIT の保持時間と、削除のリトライの待ちを無関係にするため。
  ID の文字列だけなので、想定規模では小さい)。
- バルク削除の部分失敗は、失敗した ID だけを再送する。リトライを尽くしても残れば、Store 層への
  書き込みの失敗(`StoreWriteFailedError`。`store_unavailable`)。
- どの記録を消すかの判断は呼び出し側(`crawl`)。ここは対象の選択の仕組みと削除まで。
- **限界**: `document_id` を持たない(異常な)記録が 1 ソース・1 種類に 2 件以上あると、
  `document_id` の並びが同値になり、走査が `non_unique_sort`(`StoreUnexpectedResponseError`。
  ソース削除は `failed(internal_error)`)になりうる。Crawler が書く記録は必ず `document_id` を持つ
  ので、異常なデータに対する想定外として許容する。
"""

from collections.abc import Callable

from loreley_crawler.common.errors import StoreUnavailableError, is_store_unavailable
from loreley_crawler.common.retry import Retrier
from loreley_crawler.infrastructure.opensearch import (
    BulkDeleteResult,
    RecordFilter,
    Repository,
    SortKey,
    StoredRecord,
)
from loreley_crawler.jobs.records.document_records import DocumentRecordType


class StoreWriteFailedError(StoreUnavailableError):
    """バルク削除の部分失敗が、リトライを尽くしても残った。`reason` は固定。"""

    def __init__(self) -> None:
        super().__init__("bulk_delete_incomplete")


# 走査の並べ替え。`document_id` は、1 ソース・1 種類(`record_type`)の中で一意。
SCAN_SORT = (SortKey("document_id"),)


def purge_document_records(
    repository: Repository,
    retrier: Retrier,
    *,
    source_id: str,
    record_type: DocumentRecordType,
    should_delete: Callable[[str], bool],
) -> int:
    """そのソースの `record_type` の記録のうち、`should_delete(document_id)` が真のものを削除する。

    `document_id` が読めない(形式が不正な)記録は、判断できないので消さない。削除した件数を返す。
    記録の整理(architecture 6.4)に使う。
    """

    def should_delete_record(record: StoredRecord) -> bool:
        document_id = record.source.get("document_id")
        return isinstance(document_id, str) and should_delete(document_id)

    return _purge(repository, retrier, source_id, record_type, should_delete_record)


def delete_document_records_of_source(
    repository: Repository, retrier: Retrier, *, source_id: str
) -> int:
    """そのソースの `skip`・`oversize` の記録をすべて削除する(ソース削除の順 3)。

    他のソースの記録・ロック文書・ジョブ記録は消さない。すでに記録がなければ 0 件で成功。
    形式が不正な記録も消す(ソース削除では孤児を残さない)。
    """
    return sum(
        _purge(repository, retrier, source_id, record_type, lambda _record: True)
        for record_type in DocumentRecordType
    )


def _purge(
    repository: Repository,
    retrier: Retrier,
    source_id: str,
    record_type: DocumentRecordType,
    should_delete_record: Callable[[StoredRecord], bool],
) -> int:
    record_filter = RecordFilter(equals={"record_type": record_type.value, "source_id": source_id})

    def collect_record_ids() -> list[str]:
        record_ids: list[str] = []
        with repository.scan(record_filter, sort=SCAN_SORT) as pages:
            for page in pages:
                record_ids.extend(record.id for record in page if should_delete_record(record))
        return record_ids

    record_ids = retrier.run(collect_record_ids, is_retryable_error=is_store_unavailable)
    _delete_ids_with_retry(repository, retrier, record_ids)
    return len(record_ids)


def _delete_ids_with_retry(repository: Repository, retrier: Retrier, record_ids: list[str]) -> None:
    if not record_ids:
        return
    pending_ids: tuple[str, ...] = tuple(record_ids)

    def delete_pending_ids() -> BulkDeleteResult:
        nonlocal pending_ids
        result = repository.delete_ids(pending_ids)
        pending_ids = result.failed_ids  # 次は、失敗した ID だけを再送する
        return result

    result = retrier.run(
        delete_pending_ids,
        is_retryable_error=is_store_unavailable,
        is_retryable_result=lambda outcome: bool(outcome.failed_ids),
    )
    if result.failed_ids:
        raise StoreWriteFailedError
