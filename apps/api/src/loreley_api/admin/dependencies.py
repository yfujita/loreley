"""admin の依存(組み立て済みのサービス)の入れ物と、その組み立て(D 4.1)。

`main.py` が、Reader・時計・`BlockingRunner`・設定から `build_admin_dependencies` で作り、
`create_admin_app` に渡す。ルーターは、この入れ物を受け取らない。`app.py` が必要なサービスを
個別にルーターへ渡す(D 4.3 の `create_admin_router(deps)` は、D 6章の許可表と循環するため。
0004 申し送り 1)。Crawler クライアント・Reader・プローブは、`main.py` が作って渡す。
"""

from dataclasses import dataclass

from loreley_api.admin.services.cluster_overview import ClusterOverviewService
from loreley_api.admin.services.crawl_commands import CrawlCommandService
from loreley_api.admin.services.crawler_relay import CrawlerRelay
from loreley_api.admin.services.dashboard import DashboardService
from loreley_api.admin.services.document_review import DocumentReviewService
from loreley_api.admin.services.job_queries import JobQueryService
from loreley_api.admin.services.lock_view import LockViewService
from loreley_api.admin.services.meta import MetaService
from loreley_api.admin.services.source_catalog import SourceCatalogService
from loreley_api.admin.services.source_commands import SourceCommandService
from loreley_api.admin.services.stalled_check import StalledCheck
from loreley_api.admin.settings import AdminSettings
from loreley_api.common.clock import Clock
from loreley_api.common.concurrency import BlockingRunner
from loreley_api.infrastructure.crawler_client import CrawlerClient
from loreley_api.infrastructure.opensearch import (
    ClusterReader,
    CountsReader,
    DeletionsReader,
    JobsReader,
    OpenSearchHealthCheck,
    SearchIndexReader,
    SourcesReader,
)
from loreley_api.infrastructure.probes import HttpHealthCheck, WebDistCheck


@dataclass(frozen=True)
class AdminReaders:
    """`main.py` が作る OpenSearch の Reader(Protocol)。"""

    sources: SourcesReader
    jobs: JobsReader
    deletions: DeletionsReader
    search_index: SearchIndexReader
    counts: CountsReader
    cluster: ClusterReader


@dataclass(frozen=True)
class AdminProbes:
    """`main.py` が作る死活確認のプローブ(Protocol。EP-13)。"""

    http: HttpHealthCheck
    opensearch: OpenSearchHealthCheck
    web_dist: WebDistCheck


@dataclass(frozen=True)
class AdminDependencies:
    source_catalog: SourceCatalogService
    source_commands: SourceCommandService
    crawl_commands: CrawlCommandService
    document_review: DocumentReviewService
    job_queries: JobQueryService
    cluster_overview: ClusterOverviewService
    dashboard: DashboardService
    meta: MetaService


def build_admin_dependencies(
    *,
    settings: AdminSettings,
    clock: Clock,
    runner: BlockingRunner,
    readers: AdminReaders,
    crawler: CrawlerClient,
    probes: AdminProbes,
) -> AdminDependencies:
    stalled_check = StalledCheck(jobs=readers.jobs, runner=runner)
    lock_view = LockViewService(
        jobs=readers.jobs,
        runner=runner,
        grace_seconds=settings.admitting_lock_grace_seconds,
    )
    relay = CrawlerRelay(runner=runner, lock_view=lock_view, clock=clock)
    return AdminDependencies(
        source_catalog=SourceCatalogService(
            sources=readers.sources,
            jobs=readers.jobs,
            search_index=readers.search_index,
            counts=readers.counts,
            lock_view=lock_view,
            stalled_check=stalled_check,
            runner=runner,
            clock=clock,
        ),
        source_commands=SourceCommandService(crawler=crawler, relay=relay),
        crawl_commands=CrawlCommandService(crawler=crawler, relay=relay),
        document_review=DocumentReviewService(
            sources=readers.sources,
            jobs=readers.jobs,
            search_index=readers.search_index,
            counts=readers.counts,
            runner=runner,
        ),
        job_queries=JobQueryService(
            jobs=readers.jobs,
            sources=readers.sources,
            deletions=readers.deletions,
            stalled_check=stalled_check,
            runner=runner,
            clock=clock,
        ),
        cluster_overview=ClusterOverviewService(
            cluster=readers.cluster, runner=runner, clock=clock
        ),
        dashboard=DashboardService(
            http_probe=probes.http,
            opensearch_probe=probes.opensearch,
            web_probe=probes.web_dist,
            runner=runner,
            clock=clock,
            crawler_url=settings.crawler_url,
            indexer_url=settings.indexer_url,
            dashboards_health_url=settings.dashboards_health_url,
            embedding_health_url=settings.embedding_health_url,
            llm_health_url=settings.llm_health_url,
            web_dist_dir=settings.web_dist_dir,
            probe_timeout_seconds=settings.probe_timeout_seconds,
        ),
        meta=MetaService(
            cron_timezone=settings.cron_timezone, dashboards_url=settings.dashboards_url
        ),
    )
