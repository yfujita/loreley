"""Store 層(`loreley-deletions`、`loreley-jobs`)の OpenSearch 実装。1 インスタンスが 1 索引を担う。

`term` による絞り込みとソートは、対象のフィールドが keyword であることが前提(仮定義。
`loreley-deletions` のマッピングは未決。schema U-2)。
"""

from collections.abc import Mapping, Sequence
from typing import Any

from opensearchpy import OpenSearch

from loreley_indexer.infrastructure.opensearch.client_calls import (
    delete_document,
    fetch_stored_document,
    index_document,
    refresh_index,
    run_query,
)
from loreley_indexer.infrastructure.opensearch.queries import RecordFilter, SortKey
from loreley_indexer.infrastructure.opensearch.results import (
    DeleteOutcome,
    StoredDocument,
    WriteOutcome,
)
from loreley_indexer.infrastructure.opensearch.store import LIST_MAX_SIZE, StoreRepository


class OpenSearchStore(StoreRepository):
    def __init__(self, client: OpenSearch, index_name: str) -> None:
        self._client = client
        self._index_name = index_name

    def fetch(self, record_id: str) -> StoredDocument | None:
        return fetch_stored_document(self._client, self._index_name, record_id)

    def list_records(
        self, record_filter: RecordFilter, sort: Sequence[SortKey], *, limit: int
    ) -> list[StoredDocument]:
        if not 1 <= limit <= LIST_MAX_SIZE:
            raise ValueError(f"limit must be between 1 and {LIST_MAX_SIZE}")
        body = {
            "query": build_record_query(record_filter),
            "sort": [{key.field_name: "desc" if key.descending else "asc"} for key in sort],
            "size": limit,
            "seq_no_primary_term": True,
        }
        # 一覧は検索のため、直前の書き込みを見落とさないよう先に refresh する
        # (Store 層の索引は小さい)。
        refresh_index(self._client, self._index_name)
        response = run_query(lambda: self._client.search(index=self._index_name, body=body))
        return [
            StoredDocument(
                id=hit["_id"],
                source=hit["_source"],
                seq_no=hit["_seq_no"],
                primary_term=hit["_primary_term"],
            )
            for hit in response["hits"]["hits"]
        ]

    def save(self, record_id: str, body: Mapping[str, Any]) -> WriteOutcome:
        return index_document(self._client, self._index_name, record_id, body)

    def replace_if_unchanged(
        self, record_id: str, body: Mapping[str, Any], *, seq_no: int, primary_term: int
    ) -> WriteOutcome:
        return index_document(
            self._client,
            self._index_name,
            record_id,
            body,
            if_seq_no=seq_no,
            if_primary_term=primary_term,
        )

    def delete(self, record_id: str) -> DeleteOutcome:
        return delete_document(self._client, self._index_name, record_id)


def build_record_query(record_filter: RecordFilter) -> dict[str, Any]:
    filters: list[dict[str, Any]] = [
        {"term": {name: value}} for name, value in record_filter.equals.items()
    ]
    filters += [{"terms": {name: list(values)}} for name, values in record_filter.one_of.items()]
    filters += [{"exists": {"field": name}} for name in record_filter.exists]
    must_not = [{"exists": {"field": name}} for name in record_filter.missing]
    if not filters and not must_not:
        return {"match_all": {}}
    return {"bool": {"filter": filters, "must_not": must_not}}
