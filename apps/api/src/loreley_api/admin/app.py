"""Admin API のサブアプリ(`/api/admin/v1`。D 4.2・4.12(c))。

`install_common_http` は呼ばない(外側の `create_app` がマウント時に設置する。二重になるため)。
対話型ドキュメントは常に無効、末尾スラッシュはリダイレクトしない(A 5.1・5.4)。
サブアプリを素の `FastAPI(...)` で作ると `/openapi.json` が既定で公開されるので、`openapi_url` も
明示する(`tests/architecture/test_http_rules.py` が強制する)。
"""

from fastapi import FastAPI

from loreley_api.admin.dependencies import AdminDependencies
from loreley_api.admin.routers import create_admin_router


def create_admin_app(deps: AdminDependencies) -> FastAPI:
    """`deps` のサービスを、ルーターに個別に渡して組み立てる。"""
    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )
    app.include_router(
        create_admin_router(
            source_catalog=deps.source_catalog,
            source_commands=deps.source_commands,
            crawl_commands=deps.crawl_commands,
            document_review=deps.document_review,
            job_queries=deps.job_queries,
            cluster_overview=deps.cluster_overview,
            dashboard=deps.dashboard,
            meta=deps.meta,
        )
    )
    return app
