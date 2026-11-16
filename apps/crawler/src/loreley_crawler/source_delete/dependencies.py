"""`source_delete` が使う部品の束(`main.py` が組み立てて注入する)。"""

from dataclasses import dataclass

from loreley_crawler.infrastructure.indexer_client import IndexerClient
from loreley_crawler.jobs import DocumentRecords
from loreley_crawler.sources import SourceStore


@dataclass(frozen=True)
class SourceDeleteDependencies:
    source_store: SourceStore
    indexer_client: IndexerClient
    document_records: DocumentRecords
