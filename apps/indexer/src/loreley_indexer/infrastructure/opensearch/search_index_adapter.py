"""検索インデックスの OpenSearch 実装(opensearch-py の同期クライアント)。

マッピングは未決(arch U-7)。`document_id` を keyword としてソートに使う前提は仮定義で、
実機で食い違えばここだけを直す。
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.exceptions import TransportError

from loreley_indexer.common.timestamps import format_instant
from loreley_indexer.infrastructure.opensearch.classification import classify_failure
from loreley_indexer.infrastructure.opensearch.client_calls import (
    delete_document,
    fetch_stored_document,
    index_document,
    refresh_index,
    run_query,
)
from loreley_indexer.infrastructure.opensearch.errors import OpenSearchUnexpectedResponseError
from loreley_indexer.infrastructure.opensearch.queries import DocumentFilter
from loreley_indexer.infrastructure.opensearch.results import (
    DeleteByQueryResult,
    DeleteOutcome,
    LastSeenOutcome,
    StoredDocument,
    Unchanged,
    Updated,
    WriteOutcome,
)
from loreley_indexer.infrastructure.opensearch.search_index import SearchIndexRepository

# 文字列ではなく Instant にパースして比べる(秒精度やオフセット付きの表記が混ざっても、
# 時刻の順序で比べるため。arch 3.3)。スクリプト本体は固定し、値は params で渡す。
# 現在値より新しいときだけ書き、それ以外は noop にする。実機での確認は U-31(7)。
LAST_SEEN_AT_MAX_SCRIPT = (
    "Instant incoming = Instant.parse(params.last_seen_at); "
    "def current = ctx._source.last_seen_at; "
    "if (current == null || Instant.parse(current).isBefore(incoming)) "
    "{ ctx._source.last_seen_at = params.last_seen_at; } "
    "else { ctx.op = 'none'; }"
)

# 削除の再確認に必要な項目(`source_id` の照合と `last_seen_at` による TTL の再確認)。
FETCH_FOR_DELETION_FIELDS = ("source_id", "last_seen_at")

SORT_FIELD = "document_id"
COUNT_IDS_CHUNK_SIZE = 1000


class OpenSearchSearchIndexRepository(SearchIndexRepository):
    def __init__(
        self,
        client: OpenSearch,
        index_name: str,
        *,
        update_retry_on_conflict: int,
        delete_by_query_client: OpenSearch,
        delete_by_query_timeout_seconds: float,
    ) -> None:
        """`delete_by_query_client` は、タイムアウトで再送しない専用のクライアント(P4)。

        再送の抑止はクライアントの設定で、リクエストごとには切り替えられないため、別のクライアントを
        受け取る(`connection.create_delete_by_query_client`)。
        """
        self._client = client
        self._index_name = index_name
        self._update_retry_on_conflict = update_retry_on_conflict
        self._delete_by_query_client = delete_by_query_client
        self._delete_by_query_timeout_seconds = delete_by_query_timeout_seconds

    def fetch(self, document_id: str) -> StoredDocument | None:
        return fetch_stored_document(self._client, self._index_name, document_id)

    def fetch_for_deletion(self, document_id: str) -> StoredDocument | None:
        return fetch_stored_document(
            self._client,
            self._index_name,
            document_id,
            source_includes=FETCH_FOR_DELETION_FIELDS,
        )

    def create(self, document_id: str, source: Mapping[str, Any]) -> WriteOutcome:
        return index_document(self._client, self._index_name, document_id, source, op_type="create")

    def replace_if_unchanged(
        self, document_id: str, source: Mapping[str, Any], *, seq_no: int, primary_term: int
    ) -> WriteOutcome:
        return index_document(
            self._client,
            self._index_name,
            document_id,
            source,
            if_seq_no=seq_no,
            if_primary_term=primary_term,
        )

    def raise_last_seen_at(self, document_id: str, last_seen_at: datetime) -> LastSeenOutcome:
        body = {
            "script": {
                "lang": "painless",
                "source": LAST_SEEN_AT_MAX_SCRIPT,
                "params": {"last_seen_at": format_instant(last_seen_at)},
            }
        }
        try:
            response = self._client.update(
                index=self._index_name,
                id=document_id,
                body=body,
                retry_on_conflict=self._update_retry_on_conflict,
            )
        except TransportError as error:
            return classify_failure(error)
        match response.get("result"):
            case "updated":
                return Updated()
            case "noop":
                return Unchanged()
            case other:
                raise OpenSearchUnexpectedResponseError(f"update_result_{other}")

    def delete_if_unchanged(
        self, document_id: str, *, seq_no: int, primary_term: int
    ) -> DeleteOutcome:
        return delete_document(
            self._client,
            self._index_name,
            document_id,
            if_seq_no=seq_no,
            if_primary_term=primary_term,
        )

    def search_document_ids(
        self, document_filter: DocumentFilter, *, page_size: int, after: str | None
    ) -> list[str]:
        body: dict[str, Any] = {
            "query": build_document_query(document_filter),
            "sort": [{SORT_FIELD: "asc"}],
            "size": page_size,
            "_source": False,
            "track_total_hits": False,
        }
        if after is not None:
            body["search_after"] = [after]
        response = run_query(lambda: self._client.search(index=self._index_name, body=body))
        return [hit["_id"] for hit in response["hits"]["hits"]]

    def count(self, document_filter: DocumentFilter) -> int:
        body = {"query": build_document_query(document_filter)}
        response = run_query(lambda: self._client.count(index=self._index_name, body=body))
        return response["count"]

    def count_existing_ids(self, document_ids: Sequence[str]) -> int:
        total = 0
        for start in range(0, len(document_ids), COUNT_IDS_CHUNK_SIZE):
            chunk = list(document_ids[start : start + COUNT_IDS_CHUNK_SIZE])
            total += self._count_ids_chunk(chunk)
        return total

    def refresh(self) -> None:
        refresh_index(self._client, self._index_name)

    def delete_by_query(self, document_filter: DocumentFilter) -> DeleteByQueryResult:
        if document_filter.source_id is None:
            raise ValueError("delete_by_query requires source_id")
        body = {"query": build_document_query(document_filter)}
        response = run_query(
            lambda: self._delete_by_query_client.delete_by_query(
                index=self._index_name,
                body=body,
                conflicts="proceed",
                request_timeout=self._delete_by_query_timeout_seconds,
            )
        )
        return DeleteByQueryResult(
            deleted=response.get("deleted", 0),
            version_conflicts=response.get("version_conflicts", 0),
            failure_count=len(response.get("failures", [])),
        )

    def _count_ids_chunk(self, document_ids: list[str]) -> int:
        body = {"query": {"ids": {"values": document_ids}}}
        response = run_query(lambda: self._client.count(index=self._index_name, body=body))
        return response["count"]


def build_document_query(document_filter: DocumentFilter) -> dict[str, Any]:
    filters: list[dict[str, Any]] = []
    if document_filter.source_id is not None:
        filters.append({"term": {"source_id": document_filter.source_id}})
    if document_filter.summary_status is not None:
        filters.append({"term": {"summary_status": document_filter.summary_status}})
    last_seen_range: dict[str, str] = {}
    if document_filter.last_seen_at_gte is not None:
        last_seen_range["gte"] = format_instant(document_filter.last_seen_at_gte)
    if document_filter.last_seen_at_lt is not None:
        last_seen_range["lt"] = format_instant(document_filter.last_seen_at_lt)
    if last_seen_range:
        filters.append({"range": {"last_seen_at": last_seen_range}})
    if not filters:
        return {"match_all": {}}
    return {"bool": {"filter": filters}}
