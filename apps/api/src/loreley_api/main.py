"""エントリポイント: 設定の読み込み、ログ設定、機能の組み立て、起動(Composition Root)。

機能パッケージを知っているのは、`server` ではなくこのモジュールだけ。機能を足すときは、
`build_app` でその機能を作って `create_app` の口(`routers` または `mounts`)に渡す。

uvicorn は単一プロセス(ワーカー数 1)で動かす。`timeout_graceful_shutdown` は指定しない
(Indexer と同じ。AAM-P-28)。停止時は、外側の lifespan の終了でクライアントを閉じる。
起動: `python -m loreley_api.main`
"""

import logging
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from starlette.types import Lifespan

from loreley_api.admin import (
    ADMIN_API_PREFIX,
    AdminProbes,
    AdminReaders,
    build_admin_dependencies,
    create_admin_app,
)
from loreley_api.common.clock import SystemClock
from loreley_api.common.concurrency import BlockingRunner
from loreley_api.common.logging_setup import configure_logging
from loreley_api.config import ApiConfig, load_config
from loreley_api.health import HEALTH_PATH, create_health_router
from loreley_api.infrastructure.crawler_client import HttpCrawlerClient
from loreley_api.infrastructure.opensearch import (
    OpenSearchClusterReader,
    OpenSearchCountsReader,
    OpenSearchDeletionsReader,
    OpenSearchHealthProbe,
    OpenSearchJobsReader,
    OpenSearchSearchIndexReader,
    OpenSearchSourcesReader,
    create_probe_connection,
    create_read_connection,
)
from loreley_api.infrastructure.probes import HttpHealthProbe, WebDistProbe
from loreley_api.server import SubAppMount, create_app

logger = logging.getLogger(__name__)


def close_all(closers: Sequence[Callable[[], None]]) -> None:
    """すべての `close` を呼ぶ。1 つの失敗が、残りを閉じるのを止めない。

    例外のメッセージは、接続先や ID を含みうるので出さず、クラス名だけを残す。
    """
    for close in closers:
        try:
            close()
        except Exception as error:
            logger.error("failed to close a client: error=%s", type(error).__name__)


def build_lifespan(closers: Sequence[Callable[[], None]]) -> Lifespan[FastAPI]:
    """終了時に `closers` を呼ぶ lifespan。マウントしたサブアプリ自身の lifespan は実行されない
    (Starlette の挙動)ので、クライアントを閉じる処理は外側のアプリに置く。
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            close_all(closers)

    return lifespan


def build_app(config: ApiConfig) -> FastAPI:
    """外部に接続せずに、アプリを組み立てる。

    `/healthz` は、コンテナの確認が数秒おきに呼ぶため、アクセスログを DEBUG にする。
    """
    # 生成したクライアントの `close` をここに足す(終了時に lifespan が閉じる)。
    closers: list[Callable[[], None]] = []
    opensearch = create_read_connection(config.opensearch)
    closers.append(opensearch.close)
    index_names = config.index_names
    readers = AdminReaders(
        sources=OpenSearchSourcesReader(opensearch.client, sources_index=index_names.sources),
        jobs=OpenSearchJobsReader(opensearch.client, jobs_index=index_names.jobs),
        deletions=OpenSearchDeletionsReader(
            opensearch.client, deletions_index=index_names.deletions
        ),
        search_index=OpenSearchSearchIndexReader(
            opensearch.client, search_index_alias=index_names.search
        ),
        counts=OpenSearchCountsReader(
            opensearch.client,
            jobs_index=index_names.jobs,
            search_index_alias=index_names.search,
        ),
        cluster=OpenSearchClusterReader(opensearch.client),
    )
    crawler = HttpCrawlerClient(config.crawler_client)
    closers.append(crawler.close)
    # 死活確認(EP-13)は、読み取りとは別のクライアント(短いタイムアウト・再試行なし)で行う。
    opensearch_probe_connection = create_probe_connection(config.opensearch)
    closers.append(opensearch_probe_connection.close)
    http_probe = HttpHealthProbe(config.http_probe)
    closers.append(http_probe.close)
    probes = AdminProbes(
        http=http_probe,
        opensearch=OpenSearchHealthProbe(opensearch_probe_connection.client),
        web_dist=WebDistProbe(),
    )
    admin_dependencies = build_admin_dependencies(
        settings=config.admin,
        clock=SystemClock(),
        runner=BlockingRunner(),
        readers=readers,
        crawler=crawler,
        probes=probes,
    )
    return create_app(
        routers=[create_health_router()],
        mounts=[
            SubAppMount(
                ADMIN_API_PREFIX,
                create_admin_app(admin_dependencies, openapi_enabled=config.admin.openapi_enabled),
            )
        ],
        debug_access_log_paths={HEALTH_PATH},
        lifespan=build_lifespan(closers),
    )


def main() -> None:
    # 設定が不正なら `ConfigError`(値を含まない)で、ここで異常終了する。
    config = load_config()
    configure_logging(level=config.log_level)
    app = build_app(config)
    # アプリケーションのオブジェクトを渡すので単一プロセス(ワーカーは増やさない)。
    # ログの設定は `configure_logging` に任せ(`log_config=None`)、uvicorn のアクセスログは
    # ID を含む実際のパスを出すため無効にする(自前のアクセスログを使う)。
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
