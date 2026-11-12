"""すべてのリクエストに共通の処理: 受付の可否、アクセスログ、想定外の例外の吸収。

- 起動時の整理が終わる(`ready` が立つ)までは、どのパスにも 503 `unavailable` を返す。
  HTTP の受け付けは整理の完了後に始める起動順(module 5.6)を、サーバ実装に依らず守るための
  二重の防御。
- アクセスログは自前で出す(uvicorn のアクセスログは無効にする)。出すのはメソッド、
  ルートのテンプレート(`/sources/{source_id}/last-seen`。ID を含む実際のパスではない)、
  ステータス、所要時間だけ(R9)。ルートに当たらなかったリクエストはパスを出さない。
- 想定外の例外は 500 `internal_error` にして、再送出しない(再送出するとサーバがスタックトレースを
  ログに出し、入力値を含みうるため)。
"""

import logging
import threading
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from loreley_indexer.api.errors import (
    error_response,
    internal_error_response,
    log_unexpected_error,
)

access_logger = logging.getLogger("loreley_indexer.api.access")

UNMATCHED_ROUTE = "-"


class RequestGuardMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, ready: threading.Event) -> None:
        super().__init__(app)
        self._ready = ready

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started_at = time.monotonic()
        response = await self._respond(request, call_next)
        elapsed_ms = (time.monotonic() - started_at) * 1000
        access_logger.info(
            "%s %s %d %.1fms",
            request.method,
            _route_template(request),
            response.status_code,
            elapsed_ms,
        )
        return response

    async def _respond(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._ready.is_set():
            return error_response(503, "unavailable", "the service is starting up", retryable=True)
        try:
            return await call_next(request)
        except Exception as error:
            log_unexpected_error(error)
            return internal_error_response()


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", UNMATCHED_ROUTE)
