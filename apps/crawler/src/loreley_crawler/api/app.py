"""FastAPI アプリケーションの組み立て(module 4.1)。

認証なし(MVP。内部ネットワークだけに公開する)。OpenAPI のドキュメントのエンドポイントは公開しない
(内部 API で、契約は設計書が正)。起動時の回復が終わるまで受付を始めない起動順は `main.py` が守る
(アプリケーションは、回復の後に作る)ので、ここに受付の可否の状態は持たない。
"""

from fastapi import FastAPI

from loreley_crawler.api.dependencies import ApiDependencies
from loreley_crawler.api.errors import register_error_handlers
from loreley_crawler.api.middleware import RequestGuardMiddleware
from loreley_crawler.api.routes import build_router


def create_app(dependencies: ApiDependencies) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    register_error_handlers(app)
    app.include_router(build_router(dependencies))
    app.add_middleware(RequestGuardMiddleware)
    return app
