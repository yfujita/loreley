"""FastAPI アプリケーションの組み立て(module 4.1)。

認証なし(MVP)。起動・停止の処理(`lifespan`)と、起動完了の合図(`ready`)は `main.py` が渡す。
OpenAPI のドキュメントのエンドポイントは公開しない(内部 API で、契約は設計書が正)。
"""

import threading
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI

from loreley_indexer.api.config import ApiConfig
from loreley_indexer.api.dependencies import ApiDependencies
from loreley_indexer.api.errors import register_error_handlers
from loreley_indexer.api.middleware import RequestGuardMiddleware
from loreley_indexer.api.routes import build_router

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_api_app(
    *,
    dependencies: ApiDependencies,
    config: ApiConfig,
    ready: threading.Event,
    lifespan: Lifespan | None = None,
) -> FastAPI:
    """`ready` が立つまで、すべてのリクエストを 503 にする。起動時の整理の完了後に立てること。"""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(build_router(dependencies=dependencies, config=config))
    app.add_middleware(RequestGuardMiddleware, ready=ready)
    return app
