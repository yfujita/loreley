"""すべてのリクエストに共通の処理: アクセスログ、`Cache-Control: no-store`、想定外の例外の吸収。

- アクセスログは自前で出す(uvicorn のアクセスログは無効にする)。出すのはメソッド、
  ルートのテンプレート(`/items/{item_id}`。ID を含む実際のパスではない)、ステータス、
  所要時間だけ(A 5.5)。ルートに当たらなかったリクエストはパスを出さず `-`。
- `/api/` の応答にだけ `Cache-Control: no-store` を付ける(A 5.1。AAM-P-26)。
- 想定外の例外は 500 `internal_error` にして、再送出しない(再送出すると uvicorn が
  メッセージを含むトレースバックを出し、入力値を含みうるため)。

マウントしたサブアプリの下でも、アクセスログは外側のアプリが 1 回だけ出す。外側の middleware は
サブアプリの処理が終わった後に同じ `scope` を読むので、サブアプリが決めたルートと、マウントの
接頭辞(`root_path`)が見えるためである(`_route_template`)。サブアプリには、例外の吸収のため
この middleware を `log_access=False` で別に設置する(サブアプリ自身の最外殻の Starlette が
想定外の例外を text/plain の 500 にして再送出するため)。
"""

import logging
import time
from collections.abc import Collection

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Scope

from loreley_api.common.http.errors import internal_error_response, log_unexpected_error

access_logger = logging.getLogger("loreley_api.access")

UNMATCHED_ROUTE = "-"
NO_STORE_PATH_PREFIX = "/api/"


class CommonHttpMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, app: ASGIApp, *, debug_access_log_paths: Collection[str], log_access: bool
    ) -> None:
        super().__init__(app)
        self._debug_access_log_paths = frozenset(debug_access_log_paths)
        self._log_access = log_access

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started_at = time.monotonic()
        response = await self._respond(request, call_next)
        if request.url.path.startswith(NO_STORE_PATH_PREFIX):
            response.headers["Cache-Control"] = "no-store"
        if self._log_access:
            elapsed_ms = (time.monotonic() - started_at) * 1000
            route_template = _route_template(request.scope)
            level = (
                logging.DEBUG if route_template in self._debug_access_log_paths else logging.INFO
            )
            access_logger.log(
                level,
                "%s %s %d %.1fms",
                request.method,
                route_template,
                response.status_code,
                elapsed_ms,
            )
        return response

    async def _respond(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception as error:
            log_unexpected_error(error)
            return internal_error_response()


def _route_template(scope: Scope) -> str:
    """マウントの接頭辞つきのルートのテンプレート。ルートに当たらなければ `-`。

    サブアプリの `route.path` はマウントの接頭辞を含まない。マウントを通ったときだけ
    (`app_root_path` が `scope` に入る)、`root_path` に足された接頭辞を前に付ける。
    サブアプリ内の `Mount` 配下と、外側アプリの `root_path` はテストで固定している。サブアプリの中に
    サブアプリをマウントする入れ子は未検証。

    `Mount` のように `methods` を持たないものは、リクエストの終点のルートではなく(接頭辞だけが
    当たった)、`path` から終点のテンプレートを作れない。そのときも `-`(パスを出さない)。
    """
    route = scope.get("route")
    route_path = getattr(route, "path", None)
    if route_path is None or not hasattr(route, "methods"):
        return UNMATCHED_ROUTE
    app_root_path = scope.get("app_root_path")
    if app_root_path is None:
        return route_path
    return scope["root_path"].removeprefix(app_root_path) + route_path
