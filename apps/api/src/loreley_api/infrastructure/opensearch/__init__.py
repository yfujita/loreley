"""OpenSearch の読み取り専用アクセス(D 4.8)。

`admin` が import するのは、`ports` の Protocol と型だけ(R6)。`main.py` は、接続の生成
(`create_read_connection`・`create_probe_connection`)と Reader の組み立てだけを使う。
`health_probe` は、EP-13 の実装時に足す。
"""

from loreley_api.infrastructure.opensearch.cluster_reader import OpenSearchClusterReader
from loreley_api.infrastructure.opensearch.config import IndexNames, OpenSearchConnectionConfig
from loreley_api.infrastructure.opensearch.connection import (
    ReadOnlyConnection,
    create_probe_connection,
    create_read_connection,
)
from loreley_api.infrastructure.opensearch.counts_reader import OpenSearchCountsReader
from loreley_api.infrastructure.opensearch.deletions_reader import OpenSearchDeletionsReader
from loreley_api.infrastructure.opensearch.jobs_reader import OpenSearchJobsReader
from loreley_api.infrastructure.opensearch.ports import (
    ClusterReader,
    ClusterSnapshot,
    CountsReader,
    CountTarget,
    DeletionsReader,
    JobListQuery,
    JobsReader,
    Page,
    PageRequest,
    RecordResults,
    SearchIndexReader,
    Source,
    SourceJobsSummary,
    SourcesReader,
    StoredRecord,
)
from loreley_api.infrastructure.opensearch.readonly_client import ReadOnlyOpenSearch
from loreley_api.infrastructure.opensearch.search_index_reader import OpenSearchSearchIndexReader
from loreley_api.infrastructure.opensearch.sources_reader import OpenSearchSourcesReader

__all__ = [
    "ClusterReader",
    "ClusterSnapshot",
    "CountTarget",
    "CountsReader",
    "DeletionsReader",
    "IndexNames",
    "JobListQuery",
    "JobsReader",
    "OpenSearchClusterReader",
    "OpenSearchConnectionConfig",
    "OpenSearchCountsReader",
    "OpenSearchDeletionsReader",
    "OpenSearchJobsReader",
    "OpenSearchSearchIndexReader",
    "OpenSearchSourcesReader",
    "Page",
    "PageRequest",
    "ReadOnlyConnection",
    "ReadOnlyOpenSearch",
    "RecordResults",
    "SearchIndexReader",
    "Source",
    "SourceJobsSummary",
    "SourcesReader",
    "StoredRecord",
    "create_probe_connection",
    "create_read_connection",
]
