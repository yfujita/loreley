"""統一エラー形式(A 5.2)と、想定外の例外の診断情報。

応答は `{"error": {"code", "message", "retryable", "details"?}}`。`message` は固定の英語文で、
リクエストの値(本文・ID・パス)も例外のメッセージも含めない。
ログにも、値を含まない診断情報だけを出す: 例外のクラス名と、最内フレームの
`ディレクトリ/ファイル:行 関数名`(`origin`)。
"""

import logging
import traceback
from pathlib import PurePath
from typing import Any

from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

INVALID_REQUEST_MESSAGE = "the request is invalid"
INTERNAL_ERROR_MESSAGE = "an internal error occurred"


class ApiError(Exception):
    """機能パッケージが、統一エラー形式の応答にしたい失敗を表す(例: 機能固有の `code` の 4xx)。

    `message` は固定文にする(値を含めない)。ハンドラが同じ形の応答に変換する。
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message, "retryable": retryable}
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error}, headers=headers)


def internal_error_response() -> JSONResponse:
    return error_response(500, "internal_error", INTERNAL_ERROR_MESSAGE)


def describe_origin(error: BaseException) -> str:
    """例外が送出された最内フレームの `ディレクトリ/ファイル:行 関数名`。値は含めない。"""
    frames = traceback.extract_tb(error.__traceback__)
    if not frames:
        return "unknown"
    innermost = frames[-1]
    location = "/".join(PurePath(innermost.filename).parts[-2:])
    return f"{location}:{innermost.lineno} {innermost.name}"


def log_unexpected_error(error: BaseException) -> None:
    """クラス名と送出元だけを残す。メッセージは、入力値を含みうるので出さない。"""
    logger.error(
        "request failed unexpectedly: error=%s origin=%s",
        type(error).__name__,
        describe_origin(error),
    )
