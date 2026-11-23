"""検索インデックス(エイリアス)の読み取り(R-9 の EP-01 の集計・R-10・R-11。C 3.3・3.6)。

エイリアスだけを読み、`content`・`summary` などの本文は `_source` で除く。
"""

from collections.abc import Sequence

from loreley_api.common.results import Result
from loreley_api.infrastructure.opensearch import queries
from loreley_api.infrastructure.opensearch.failure import guarded_read
from loreley_api.infrastructure.opensearch.ports import MAX_EXISTENCE_IDS, Page, PageRequest
from loreley_api.infrastructure.opensearch.reading import search_page
from loreley_api.infrastructure.opensearch.readonly_client import ReadOnlyOpenSearch
from loreley_api.infrastructure.opensearch.responses import (
    as_int,
    as_list,
    as_mapping,
    as_str,
    parse_search,
)


class OpenSearchSearchIndexReader:
    def __init__(self, readonly: ReadOnlyOpenSearch, *, search_index_alias: str) -> None:
        self._readonly = readonly
        self._search_index_alias = search_index_alias

    def count_by_source(self, source_ids: Sequence[str]) -> Result[dict[str, int]]:
        return guarded_read(
            "search_index.count_by_source", "search_index", lambda: self._read_counts(source_ids)
        )

    def list_extract_failed(self, source_id: str, page: PageRequest) -> Result[Page]:
        return search_page(
            self._readonly,
            index=self._search_index_alias,
            body=queries.extract_failed_list_body(source_id, page),
            target="search_index",
            operation="search_index.list_extract_failed",
        )

    def list_summary_pending(self, source_id: str, page: PageRequest) -> Result[Page]:
        return search_page(
            self._readonly,
            index=self._search_index_alias,
            body=queries.summary_pending_list_body(source_id, page),
            target="search_index",
            operation="search_index.list_summary_pending",
        )

    def existing_ids(self, document_ids: Sequence[str]) -> Result[frozenset[str]]:
        unique_ids = tuple(dict.fromkeys(document_ids))
        if len(unique_ids) > MAX_EXISTENCE_IDS:
            raise ValueError("too many document ids")
        return guarded_read(
            "search_index.existing_ids", "search_index", lambda: self._read_existing(unique_ids)
        )

    def _read_counts(self, source_ids: Sequence[str]) -> dict[str, int]:
        unique_source_ids = tuple(dict.fromkeys(source_ids))
        if not unique_source_ids:
            return {}
        response = self._readonly.search(
            index=self._search_index_alias, body=queries.count_by_source_body(unique_source_ids)
        )
        aggregations = parse_search(response).aggregations
        buckets = as_list(as_mapping(aggregations.get("by_source")).get("buckets"))
        counted = {}
        for bucket in buckets:
            bucket_mapping = as_mapping(bucket)
            counted[as_str(bucket_mapping.get("key"))] = as_int(bucket_mapping.get("doc_count"))
        # バケットのないソース(文書が 0 件)は 0。
        return {source_id: counted.get(source_id, 0) for source_id in unique_source_ids}

    def _read_existing(self, document_ids: Sequence[str]) -> frozenset[str]:
        if not document_ids:
            return frozenset()
        response = self._readonly.search(
            index=self._search_index_alias, body=queries.existing_ids_body(document_ids)
        )
        return frozenset(hit.record_id for hit in parse_search(response).hits)
