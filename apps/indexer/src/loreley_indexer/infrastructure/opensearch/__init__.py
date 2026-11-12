"""OpenSearch の窓口(検索インデックスと Store 層)。"""

from loreley_indexer.infrastructure.opensearch.connection import (
    IndexNames,
    OpenSearchConnectionConfig,
    close_clients,
    create_delete_by_query_client,
    create_opensearch_client,
)
from loreley_indexer.infrastructure.opensearch.errors import (
    OpenSearchUnavailableError,
    OpenSearchUnexpectedResponseError,
)
from loreley_indexer.infrastructure.opensearch.jobs import JobsReader, StoreJobsReader
from loreley_indexer.infrastructure.opensearch.queries import DocumentFilter, RecordFilter, SortKey
from loreley_indexer.infrastructure.opensearch.results import (
    Conflict,
    DeleteByQueryResult,
    Deleted,
    DeleteOutcome,
    LastSeenOutcome,
    NotFound,
    Rejected,
    StoredDocument,
    Unchanged,
    Updated,
    WriteOutcome,
    Written,
)
from loreley_indexer.infrastructure.opensearch.search_index import SearchIndexRepository
from loreley_indexer.infrastructure.opensearch.search_index_adapter import (
    OpenSearchSearchIndexRepository,
)
from loreley_indexer.infrastructure.opensearch.store import StoreReader, StoreRepository
from loreley_indexer.infrastructure.opensearch.store_adapter import OpenSearchStore

__all__ = [
    "Conflict",
    "DeleteByQueryResult",
    "DeleteOutcome",
    "Deleted",
    "DocumentFilter",
    "IndexNames",
    "JobsReader",
    "LastSeenOutcome",
    "NotFound",
    "OpenSearchConnectionConfig",
    "OpenSearchSearchIndexRepository",
    "OpenSearchStore",
    "OpenSearchUnavailableError",
    "OpenSearchUnexpectedResponseError",
    "RecordFilter",
    "Rejected",
    "SearchIndexRepository",
    "SortKey",
    "StoreJobsReader",
    "StoreReader",
    "StoreRepository",
    "StoredDocument",
    "Unchanged",
    "Updated",
    "WriteOutcome",
    "Written",
    "close_clients",
    "create_delete_by_query_client",
    "create_opensearch_client",
]
