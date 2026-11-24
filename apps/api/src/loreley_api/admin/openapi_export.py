"""OpenAPI JSON の書き出し(型生成の入力。A 5.4・D 5.9。AAM-P-16)。

起動: `python -m loreley_api.admin.openapi_export <出力パス>`

サーバーを起動せず、外部にも接続しない(OpenSearch・Crawler・環境変数の設定は要らない)。
OpenAPI の生成は、ルートの定義と DTO だけから決まり、サービスを呼ばないので、どこにも
つながらない代役の依存で `create_admin_app` を組み立てる。外側のアプリの `app.openapi()` には
サブアプリのスキーマが集約されないので、サブアプリから生成する(D 4.12(c))。

`OPENAPI_ENABLED`(実行時の公開)とは関係なく、いつでも書き出せる。書き出した JSON は
リポジトリにコミットしない(置き場は、フロントエンドの型生成の手順が決める)。
"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn, cast

from loreley_api.admin.app import create_admin_app
from loreley_api.admin.dependencies import (
    AdminDependencies,
    AdminProbes,
    AdminReaders,
    build_admin_dependencies,
)
from loreley_api.admin.settings import AdminSettings
from loreley_api.common.clock import SystemClock
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


class _Unconnected:
    """どこにも接続しない代役。OpenAPI の生成では呼ばれないので、呼ばれたら失敗させる。"""

    def __getattr__(self, name: str) -> NoReturn:
        raise RuntimeError(f"the OpenAPI export does not connect anywhere: {name}")


def _build_unconnected_dependencies() -> AdminDependencies:
    unconnected = _Unconnected()
    return build_admin_dependencies(
        # 値は使われない(サービスが保持するだけ)。実在しない名前にして、誤って使われても
        # 外部に届かないようにする。
        settings=AdminSettings(
            crawler_url="http://crawler.invalid",
            indexer_url="http://indexer.invalid",
            dashboards_health_url=None,
            embedding_health_url=None,
            llm_health_url=None,
            probe_timeout_seconds=3.0,
            web_dist_dir="/nonexistent",
            cron_timezone=None,
            dashboards_url=None,
            admitting_lock_grace_seconds=60.0,
            openapi_enabled=False,
        ),
        clock=SystemClock(),
        runner=BlockingRunner(),
        readers=AdminReaders(
            sources=cast(SourcesReader, unconnected),
            jobs=cast(JobsReader, unconnected),
            deletions=cast(DeletionsReader, unconnected),
            search_index=cast(SearchIndexReader, unconnected),
            counts=cast(CountsReader, unconnected),
            cluster=cast(ClusterReader, unconnected),
        ),
        crawler=cast(CrawlerClient, unconnected),
        probes=AdminProbes(
            http=cast(HttpHealthCheck, unconnected),
            opensearch=cast(OpenSearchHealthCheck, unconnected),
            web_dist=cast(WebDistCheck, unconnected),
        ),
    )


def build_openapi_schema() -> dict[str, Any]:
    """Admin API の OpenAPI(サブアプリから生成する)。"""
    return create_admin_app(_build_unconnected_dependencies()).openapi()


def render_openapi_json() -> str:
    """キーを並べ替え、インデントを固定した JSON(同じコードなら、毎回同じ文字列。末尾は改行)。"""
    return json.dumps(build_openapi_schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m loreley_api.admin.openapi_export",
        description="Write the Admin API OpenAPI JSON. It does not connect anywhere.",
    )
    parser.add_argument("output_path", type=Path, help="the file to write (overwritten)")
    arguments = parser.parse_args(argv)
    arguments.output_path.write_text(render_openapi_json(), encoding="utf-8")


if __name__ == "__main__":
    main()
