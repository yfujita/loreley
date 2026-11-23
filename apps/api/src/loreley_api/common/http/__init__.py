"""A 5章の共通 HTTP 規約(エラー形式・アクセスログ・`no-store`)の設置口。"""

from collections.abc import Collection

from fastapi import FastAPI

from loreley_api.common.http.errors import ApiError
from loreley_api.common.http.handlers import register_error_handlers
from loreley_api.common.http.middleware import CommonHttpMiddleware

__all__ = ["ApiError", "install_common_http"]


def install_common_http(
    app: FastAPI,
    *,
    debug_access_log_paths: Collection[str] = (),
    log_access: bool = True,
) -> None:
    """例外ハンドラと middleware を `app` に設置する。

    外側のアプリとマウントするサブアプリの両方に設置する。アクセスログは外側だけが出すので、
    サブアプリには `log_access=False` を渡す。`debug_access_log_paths` は、DEBUG で出す
    ルートのテンプレート(`/healthz` など)。
    """
    register_error_handlers(app)
    app.add_middleware(
        CommonHttpMiddleware,
        debug_access_log_paths=debug_access_log_paths,
        log_access=log_access,
    )
