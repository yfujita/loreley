"""Store 層(`loreley-sources`・`loreley-jobs`)の Repository の OpenSearch 実装(module 4.8)。"""

from loreley_crawler.infrastructure.opensearch.connection import (
    OpenSearchConnectionConfig,
    close_clients,
    create_heartbeat_client,
    create_store_client,
)
from loreley_crawler.infrastructure.opensearch.opensearch_repository import OpenSearchRepository
from loreley_crawler.infrastructure.opensearch.queries import FieldValue, RecordFilter, SortKey
from loreley_crawler.infrastructure.opensearch.repository import (
    LIST_MAX_SIZE,
    RecordPages,
    Repository,
)
from loreley_crawler.infrastructure.opensearch.results import (
    AlreadyExists,
    BulkDeleteResult,
    Conflict,
    CreateOutcome,
    Deleted,
    DeleteOutcome,
    NotFound,
    ReplaceOutcome,
    StoredRecord,
    Written,
)
from loreley_crawler.infrastructure.opensearch.settings import RepositorySettings

__all__ = [
    "LIST_MAX_SIZE",
    "AlreadyExists",
    "BulkDeleteResult",
    "Conflict",
    "CreateOutcome",
    "DeleteOutcome",
    "Deleted",
    "FieldValue",
    "NotFound",
    "OpenSearchConnectionConfig",
    "OpenSearchRepository",
    "RecordFilter",
    "RecordPages",
    "ReplaceOutcome",
    "Repository",
    "RepositorySettings",
    "SortKey",
    "StoredRecord",
    "Written",
    "close_clients",
    "create_heartbeat_client",
    "create_store_client",
]
