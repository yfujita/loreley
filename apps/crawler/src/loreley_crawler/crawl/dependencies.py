"""`crawl` が使う部品の束(`main.py` が組み立てて注入する)。"""

from dataclasses import dataclass

from loreley_crawler.common.clock import Clock
from loreley_crawler.connectors.registry import ConnectorRegistry
from loreley_crawler.crawl.settings import CrawlSettings
from loreley_crawler.documents import DocumentsSettings
from loreley_crawler.infrastructure.indexer_client import IndexerClient
from loreley_crawler.jobs import DocumentRecords, JobHistory
from loreley_crawler.sources import SourceReader


@dataclass(frozen=True)
class CrawlDependencies:
    source_reader: SourceReader
    connector_registry: ConnectorRegistry
    indexer_client: IndexerClient
    document_records: DocumentRecords
    job_history: JobHistory
    clock: Clock
    settings: CrawlSettings
    documents_settings: DocumentsSettings
