"""EP の受け口(D 4.3)。EP を実装するフェーズで、ファイルごとのルーターをここで束ねる。

ルーターには `AdminDependencies` ではなく、必要なサービスを渡す。`admin.routers` は `admin` 直下
(`dependencies.py`)を import できない(R4。import すると admin → routers → admin の循環になる)。
`app.py` が、`AdminDependencies` からサービスを取り出して渡す。
"""

from fastapi import APIRouter

from loreley_api.admin.routers.crawl_operations import create_crawl_operations_router
from loreley_api.admin.routers.dashboard import create_dashboard_router
from loreley_api.admin.routers.documents import create_documents_router
from loreley_api.admin.routers.jobs import create_jobs_router
from loreley_api.admin.routers.meta import create_meta_router
from loreley_api.admin.routers.opensearch import create_opensearch_router
from loreley_api.admin.routers.sources import create_sources_router
from loreley_api.admin.services.cluster_overview import ClusterOverviewService
from loreley_api.admin.services.crawl_commands import CrawlCommandService
from loreley_api.admin.services.dashboard import DashboardService
from loreley_api.admin.services.document_review import DocumentReviewService
from loreley_api.admin.services.job_queries import JobQueryService
from loreley_api.admin.services.meta import MetaService
from loreley_api.admin.services.source_catalog import SourceCatalogService
from loreley_api.admin.services.source_commands import SourceCommandService


def create_admin_router(
    *,
    source_catalog: SourceCatalogService,
    source_commands: SourceCommandService,
    crawl_commands: CrawlCommandService,
    document_review: DocumentReviewService,
    job_queries: JobQueryService,
    cluster_overview: ClusterOverviewService,
    dashboard: DashboardService,
    meta: MetaService,
) -> APIRouter:
    router = APIRouter()
    router.include_router(create_sources_router(source_catalog, source_commands))
    router.include_router(create_crawl_operations_router(crawl_commands))
    router.include_router(create_documents_router(document_review))
    router.include_router(create_jobs_router(job_queries))
    router.include_router(create_opensearch_router(cluster_overview))
    router.include_router(create_dashboard_router(dashboard))
    router.include_router(create_meta_router(meta))
    return router
