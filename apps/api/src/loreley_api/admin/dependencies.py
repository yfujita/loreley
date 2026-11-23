"""admin の依存(組み立て済みのサービス)の入れ物と、その組み立て(D 4.1)。

`main.py` が、Reader・時計・`BlockingRunner`・設定から `build_admin_dependencies` で作り、
`create_admin_app` に渡す。ルーターは、この入れ物を受け取らない。`app.py` が必要なサービスを
個別にルーターへ渡す(D 4.3 の `create_admin_router(deps)` は、D 6章の許可表と循環するため。
0004 申し送り 1)。サービスと Reader は、EP を実装するときに足す。
"""

from dataclasses import dataclass

from loreley_api.admin.services.cluster_overview import ClusterOverviewService
from loreley_api.admin.services.job_queries import JobQueryService
from loreley_api.admin.services.meta import MetaService
from loreley_api.admin.services.stalled_check import StalledCheck
from loreley_api.admin.settings import AdminSettings
from loreley_api.common.clock import Clock
from loreley_api.common.concurrency import BlockingRunner
from loreley_api.infrastructure.opensearch import (
    ClusterReader,
    DeletionsReader,
    JobsReader,
    SourcesReader,
)


@dataclass(frozen=True)
class AdminReaders:
    """`main.py` が作る OpenSearch の Reader(Protocol)。"""

    sources: SourcesReader
    jobs: JobsReader
    deletions: DeletionsReader
    cluster: ClusterReader


@dataclass(frozen=True)
class AdminDependencies:
    job_queries: JobQueryService
    cluster_overview: ClusterOverviewService
    meta: MetaService


def build_admin_dependencies(
    *,
    settings: AdminSettings,
    clock: Clock,
    runner: BlockingRunner,
    readers: AdminReaders,
) -> AdminDependencies:
    stalled_check = StalledCheck(jobs=readers.jobs, runner=runner)
    return AdminDependencies(
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
        meta=MetaService(
            cron_timezone=settings.cron_timezone, dashboards_url=settings.dashboards_url
        ),
    )
