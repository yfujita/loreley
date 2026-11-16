"""すべてのリクエストに共通の処理: アクセスログと、想定外の例外の吸収。

- アクセスログは自前で出す(uvicorn のアクセスログは無効にする)。出すのはメソッド、ルートの
  テンプレート(`/sources/{source_id}/lock`。ID を含む実際のパスではない)、ステータス、所要時間
  だけ(R11)。ルートに当たらなかったリクエストはパスを出さない。
- 想定外の例外は 500 `internal_error` にして、再送出しない(再送出するとサーバがスタックトレースを
  ログに出し、入力値を含みうるため)。
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from loreley_crawler.api.errors import internal_error_response, log_unexpected_error

access_logger = logging.getLogger("loreley_crawler.api.access")

UNMATCHED_ROUTE = "-"
HEALTH_CHECK_ROUTE = "/healthz"


class RequestGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started_at = time.monotonic()
        response = await self._respond(request, call_next)
        elapsed_ms = (time.monotonic() - started_at) * 1000
        route = _route_template(request)
        # ヘルスチェックは間隔ごとに来る(compose で 1 日に数千回)ので DEBUG にする。
        level = logging.DEBUG if route == HEALTH_CHECK_ROUTE else logging.INFO
        access_logger.log(
            level,
            "%s %s %d %.1fms",
            request.method,
            route,
            response.status_code,
            elapsed_ms,
        )
        return response

    @staticmethod
    async def _respond(request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception as error:
            log_unexpected_error(error)
            return internal_error_response()


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", UNMATCHED_ROUTE)
