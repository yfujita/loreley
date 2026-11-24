"""`loreley-sources` の読み取り(R-1・R-2。C 3.3)。"""

from collections.abc import Sequence

from loreley_api.common.results import Result
from loreley_api.infrastructure.opensearch import queries
from loreley_api.infrastructure.opensearch.failure import ResultLimitExceededError, guarded_read
from loreley_api.infrastructure.opensearch.ports import MAX_SOURCES, StoredRecord
from loreley_api.infrastructure.opensearch.reading import fetch_documents
from loreley_api.infrastructure.opensearch.readonly_client import ReadOnlyOpenSearch
from loreley_api.infrastructure.opensearch.responses import parse_counted_search


class OpenSearchSourcesReader:
    def __init__(self, readonly: ReadOnlyOpenSearch, *, sources_index: str) -> None:
        self._readonly = readonly
        self._sources_index = sources_index

    def list_all(self) -> Result[tuple[StoredRecord, ...]]:
        return guarded_read("sources.list_all", "store", self._read_all)

    def get(self, source_id: str, fields: Sequence[str] | None) -> Result[StoredRecord | None]:
        # `fields` が空なら存在確認だけ(`_source` を返さない)。
        results = fetch_documents(
            self._readonly,
            index=self._sources_index,
            ids=[source_id],
            target="store",
            operation="sources.get",
            source_includes=fields,
            include_source=fields is None or len(fields) > 0,
        )
        return results[source_id]

    def _read_all(self) -> tuple[StoredRecord, ...]:
        response = self._readonly.search(index=self._sources_index, body=queries.sources_all_body())
        parsed = parse_counted_search(response)
        # 上限を超えると取りこぼすので、一部だけを返さず失敗にする(B 3.1)。
        if parsed.total > MAX_SOURCES:
            raise ResultLimitExceededError("too many data sources")
        return parsed.hits
