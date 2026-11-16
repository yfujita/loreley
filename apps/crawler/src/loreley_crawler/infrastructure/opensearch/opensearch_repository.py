"""`Repository` の OpenSearch 実装(module 4.8)。1 インスタンスが 1 索引を担う。

索引・マッピングは作らない(`opensearch-init` が作成・管理する。CM-K-9)。索引が作られている前提で
読み書きする。索引名は設定で与える(R7: `main.py` が、`loreley-sources` 用・`loreley-jobs` 用・
ハートビート専用の `loreley-jobs` 用の 3 つだけを作る)。
"""

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any

from opensearchpy import OpenSearch

from loreley_crawler.infrastructure.opensearch.bulk_delete import delete_ids_in_bulk
from loreley_crawler.infrastructure.opensearch.client_calls import (
    STRICT_SEARCH_PARAMS,
    create_record,
    delete_record,
    ensure_search_complete,
    fetch_record,
    refresh_index,
    replace_record,
    run_query,
    to_record,
)
from loreley_crawler.infrastructure.opensearch.queries import RecordFilter, SortKey
from loreley_crawler.infrastructure.opensearch.query_builder import (
    build_record_query,
    build_sort,
)
from loreley_crawler.infrastructure.opensearch.repository import (
    LIST_MAX_SIZE,
    RecordPages,
    Repository,
)
from loreley_crawler.infrastructure.opensearch.results import (
    BulkDeleteResult,
    CreateOutcome,
    DeleteOutcome,
    ReplaceOutcome,
    StoredRecord,
)
from loreley_crawler.infrastructure.opensearch.scan import scan_records
from loreley_crawler.infrastructure.opensearch.settings import RepositorySettings


class OpenSearchRepository(Repository):
    def __init__(
        self, client: OpenSearch, index_name: str, settings: RepositorySettings | None = None
    ) -> None:
        self._client = client
        self._index_name = index_name
        self._settings = settings or RepositorySettings()

    def fetch(self, record_id: str) -> StoredRecord | None:
        return fetch_record(self._client, self._index_name, record_id)

    def create(self, record_id: str, body: Mapping[str, Any]) -> CreateOutcome:
        return create_record(self._client, self._index_name, record_id, body)

    def replace_if_unchanged(
        self, record_id: str, body: Mapping[str, Any], *, seq_no: int, primary_term: int
    ) -> ReplaceOutcome:
        return replace_record(
            self._client,
            self._index_name,
            record_id,
            body,
            seq_no=seq_no,
            primary_term=primary_term,
        )

    def delete_if_unchanged(
        self, record_id: str, *, seq_no: int, primary_term: int
    ) -> DeleteOutcome:
        return delete_record(
            self._client, self._index_name, record_id, seq_no=seq_no, primary_term=primary_term
        )

    def list_records(
        self, record_filter: RecordFilter, sort: Sequence[SortKey], *, limit: int
    ) -> list[StoredRecord]:
        if not 1 <= limit <= LIST_MAX_SIZE:
            raise ValueError(f"limit must be between 1 and {LIST_MAX_SIZE}")
        body = {
            "query": build_record_query(record_filter),
            "sort": build_sort(sort),
            "size": limit,
            "seq_no_primary_term": True,
        }
        # 一覧は検索のため、直前の書き込みを見落とさないよう、先に refresh する
        # (Store 層の索引は小さい)。
        refresh_index(self._client, self._index_name)
        response = run_query(
            lambda: self._client.search(
                index=self._index_name, body=body, params=dict(STRICT_SEARCH_PARAMS)
            )
        )
        # 一部のシャードの失敗・タイムアウトで欠けた一覧を、成功として返さない。
        ensure_search_complete(response)
        return [to_record(hit["_id"], hit) for hit in response["hits"]["hits"]]

    def scan(
        self, record_filter: RecordFilter, *, sort: Sequence[SortKey]
    ) -> AbstractContextManager[RecordPages]:
        if not sort:
            raise ValueError("sort must include a unique tiebreaker")
        return scan_records(self._client, self._index_name, record_filter, sort, self._settings)

    def delete_ids(self, record_ids: Sequence[str]) -> BulkDeleteResult:
        return delete_ids_in_bulk(self._client, self._index_name, record_ids, self._settings)
