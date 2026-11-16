"""共通のエラー形式と、例外から HTTP 応答への写像(crawler-api 3.3)。

応答は `{"error": {"code", "message", "retryable", "details"?}}`。`message` は固定文で、リクエストの
値(本文・ID・`connector_config`・認証情報の参照名)も例外のメッセージも含めない(R11)。例外は
`config_invalid`(Connector の説明文。crawler-api 3.3 が許す唯一の例外)だけ。
ログにも、値を含まない診断情報だけを出す: 例外のクラス名、`StoreUnavailableError` の理由名、
`StoreUnexpectedResponseError` の種別名、最内フレームの `ファイル:行 関数名`(`origin`)。

写像:
- `InvalidRequestError`、FastAPI のパス検証エラー: 400 `invalid_request`(`details.errors` は項目名と
  `reason` だけ。pydantic の検証エラーは入力値を含むので、位置と型だけに変換する)
- `StoreUnavailableError`(リトライを尽くした Store 層の全体の異常): 503 `unavailable`
  (`retryable=true`)
- `StoreUnexpectedResponseError` と、想定外の例外(`middleware.py`): 500 `internal_error`
- 未定義のパス・メソッドなどの HTTP 例外: `not_found`・`method_not_allowed`・`http_error`
"""

import logging
import traceback
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError

logger = logging.getLogger(__name__)

INVALID_REQUEST_MESSAGE = "the request is invalid"
INTERNAL_ERROR_MESSAGE = "an internal error occurred"
UNAVAILABLE_MESSAGE = "the service is temporarily unavailable"
_HTTP_ERROR_CODES = {404: "not_found", 405: "method_not_allowed"}


class Reason(StrEnum):
    """`details.errors` の `reason`(crawler-api 3.3)。"""

    REQUIRED = "required"
    TYPE = "type"
    FORMAT = "format"
    READ_ONLY = "read_only"
    UNKNOWN_FIELD = "unknown_field"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class FieldError:
    field: str
    reason: Reason


class InvalidRequestError(Exception):
    """リクエストの形式不正(400 `invalid_request`)。`errors` は項目名と `reason` だけ。"""

    def __init__(self, errors: Sequence[FieldError] = ()) -> None:
        super().__init__(INVALID_REQUEST_MESSAGE)
        self.errors = tuple(errors)


class ConfigInvalidError(Exception):
    """Connector が `connector_config` の違反を返した(400 `config_invalid`)。

    `message` は Connector の説明文(項目名・違反の種類など。crawler-api 3.3)。
    """

    def __init__(self, message: str) -> None:
        super().__init__("the connector_config is invalid")
        self.message = message


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message, "retryable": retryable}
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error})


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
        f" error_type={error.error_type}" if isinstance(error, StoreUnexpectedResponseError) else ""
    )
    logger.error(
        "request failed unexpectedly: error=%s%s origin=%s",
        type(error).__name__,
        error_type,
        describe_origin(error),
    )


def _error_details(errors: Sequence[FieldError]) -> dict[str, Any]:
    return {"errors": [{"field": error.field, "reason": error.reason.value} for error in errors]}


def describe_validation_errors(errors: Sequence[Any]) -> list[FieldError]:
    """pydantic の検証エラーを、位置と `reason` だけにする。`input`・`ctx`・`msg` は使わない。"""
    return [
        FieldError(".".join(str(part) for part in error["loc"]), _reason_of(error["type"]))
        for error in errors
    ]


def _reason_of(pydantic_error_type: str) -> Reason:
    if pydantic_error_type == "missing":
        return Reason.REQUIRED
    if pydantic_error_type == "extra_forbidden":
        return Reason.UNKNOWN_FIELD
    return Reason.TYPE


async def _handle_invalid_request(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, InvalidRequestError)
    details = _error_details(error.errors) if error.errors else None
    return error_response(400, "invalid_request", INVALID_REQUEST_MESSAGE, details=details)


async def _handle_validation_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    # `errors()` の `input` と `ctx` は使わない(位置と型だけを返す)。
    field_errors = describe_validation_errors(error.errors())
    return error_response(
        400, "invalid_request", INVALID_REQUEST_MESSAGE, details=_error_details(field_errors)
    )


async def _handle_config_invalid(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, ConfigInvalidError)
    return error_response(400, "config_invalid", error.message)


async def _handle_unavailable(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StoreUnavailableError)
    logger.warning("the store is unavailable: reason=%s", error.reason)
    return error_response(503, "unavailable", UNAVAILABLE_MESSAGE, retryable=True)


async def _handle_unexpected_store_response(request: Request, error: Exception) -> JSONResponse:
    log_unexpected_error(error)
    return internal_error_response()


async def _handle_http_exception(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StarletteHTTPException)
    code = _HTTP_ERROR_CODES.get(error.status_code, "http_error")
    return error_response(error.status_code, code, "the request cannot be handled")


def register_error_handlers(app: FastAPI) -> None:
    handlers: dict[Any, Any] = {
        InvalidRequestError: _handle_invalid_request,
        RequestValidationError: _handle_validation_error,
        ConfigInvalidError: _handle_config_invalid,
        StoreUnavailableError: _handle_unavailable,
        StoreUnexpectedResponseError: _handle_unexpected_store_response,
        StarletteHTTPException: _handle_http_exception,
    }
    for exception_class, handler in handlers.items():
        app.add_exception_handler(exception_class, handler)
