"""共通のエラー形式と、例外から HTTP 応答への写像(api 3.4)。

応答は `{"error": {"code", "message", "retryable"}}`。メッセージは固定文か、検証エラーの位置と型
だけで、リクエストの値(本文、ID、秘密値)も例外のメッセージも含めない(R9)。
ログにも、値を含まない診断情報だけを出す: 例外のクラス名、`UnavailableError` の原因の種別名、
`UnexpectedResponseError` の種別名、最内フレームの `ファイル:行 関数名`(`origin`)。メッセージ・
ローカル変数・スタックトレースは、入力値を含みうるので出さない。

写像:
- `ContractError`(受理条件の拒否・通知の 409、Status の 404、ロック不所有の 409):
  `status_code`・`code`・`message`・`retryable` をそのまま使う
- `InvalidRequestError`、FastAPI のパス検証エラー: 400 `invalid_request`(位置と型)
- `ValueError`(ドメインが形式不正として送出するもの): 400 `invalid_request`(固定文)。ドメインの
  形式不正以外の `ValueError`(バグ・ライブラリ)も同じ経路に来て、Crawler には 400 としか伝わらない
  ので、サーバ側の手がかりとして warning を残す
- `UnavailableError`(OpenSearch の全体異常など): 503 `unavailable`(`retryable=true`)
- そのほかの `IndexerError`(想定外の応答・不正な記録など)と、想定外の例外: 500 `internal_error`
"""

import logging
import traceback
from pathlib import PurePath
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from loreley_indexer.api.schemas import describe_validation_errors
from loreley_indexer.common.errors import (
    ContractError,
    IndexerError,
    UnavailableError,
    UnexpectedResponseError,
)

logger = logging.getLogger(__name__)

INTERNAL_ERROR_MESSAGE = "an internal error occurred"
_HTTP_ERROR_CODES = {404: "not_found", 405: "method_not_allowed"}


class InvalidRequestError(Exception):
    """リクエストの形式不正(400)。`message` は固定文か、位置と型だけ(入力値を含めない)。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def error_response(
    status_code: int, code: str, message: str, *, retryable: bool = False
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "retryable": retryable}}
    return JSONResponse(status_code=status_code, content=body)


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
    """クラス名・種別名・送出元だけを残す。メッセージは、入力値を含みうるので出さない。"""
    error_type = (
        f" error_type={error.error_type}" if isinstance(error, UnexpectedResponseError) else ""
    )
    logger.error(
        "request failed unexpectedly: error=%s%s origin=%s",
        type(error).__name__,
        error_type,
        describe_origin(error),
    )


async def _handle_contract_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, ContractError)
    return error_response(error.status_code, error.code, error.message, retryable=error.retryable)


async def _handle_invalid_request(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, InvalidRequestError)
    return error_response(400, "invalid_request", error.message)


async def _handle_validation_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    # `errors()` の `input` と `ctx` は使わない(位置と型だけを返す)。
    return error_response(400, "invalid_request", describe_validation_errors(error.errors()))


async def _handle_value_error(request: Request, error: Exception) -> JSONResponse:
    # メッセージは使わない。ドメインの検証は入力値を含めない作りだが、ライブラリの例外が値を
    # 含む場合に備えて、固定文にする。
    logger.warning(
        "domain rejected the request: error=%s origin=%s",
        type(error).__name__,
        describe_origin(error),
    )
    return error_response(400, "invalid_request", "the request is invalid")


async def _handle_unavailable(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, UnavailableError)
    logger.warning("the indexer is unavailable: reason=%s", error.reason)
    return error_response(
        503, "unavailable", "the service is temporarily unavailable", retryable=True
    )


async def _handle_indexer_error(request: Request, error: Exception) -> JSONResponse:
    log_unexpected_error(error)
    return internal_error_response()


async def _handle_http_exception(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StarletteHTTPException)
    code = _HTTP_ERROR_CODES.get(error.status_code, "http_error")
    return error_response(error.status_code, code, "the request cannot be handled")


def register_error_handlers(app: FastAPI) -> None:
    handlers: dict[Any, Any] = {
        ContractError: _handle_contract_error,
        InvalidRequestError: _handle_invalid_request,
        RequestValidationError: _handle_validation_error,
        ValueError: _handle_value_error,
        UnavailableError: _handle_unavailable,
        IndexerError: _handle_indexer_error,
        StarletteHTTPException: _handle_http_exception,
    }
    for exception_class, handler in handlers.items():
        app.add_exception_handler(exception_class, handler)
