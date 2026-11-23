"""例外から統一エラー形式への変換(A 5.2)。

FastAPI の標準の検証エラー(422)と `HTTPException` の本文は使わず、すべて統一形式にする。
想定外の例外(`Exception`)はここでは扱わない。Starlette の `Exception` のハンドラは応答の後に
例外を再送出し、uvicorn がメッセージを含むトレースバックを出すため、`middleware.py` が捕捉する。
"""

import re
import unicodedata
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from loreley_api.common.http.errors import INVALID_REQUEST_MESSAGE, ApiError, error_response

MAX_FIELD_NAME_CHARS = 100
REPLACEMENT_CHARACTER = "�"

_LOCATION_NAMES = frozenset({"body", "query", "path", "header", "cookie"})
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")
_NAMED_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}

_HTTP_ERRORS = {
    404: ("not_found", "the path is not defined"),
    405: ("method_not_allowed", "the method is not allowed"),
}
_OTHER_HTTP_ERROR = ("http_error", "the request cannot be handled")

_RANGE_ERROR_TYPES = frozenset(
    {
        "greater_than",
        "greater_than_equal",
        "less_than",
        "less_than_equal",
        "too_short",
        "too_long",
        "multiple_of",
    }
)
_UNSUPPORTED_ERROR_TYPES = frozenset({"literal_error", "enum"})


def reason_of(pydantic_error_type: str) -> str:
    """pydantic の検証エラーの `type` を、A 5.2 の `reason` にする(未知の type は `format`)。"""
    if pydantic_error_type == "missing":
        return "required"
    if pydantic_error_type == "extra_forbidden":
        return "unknown_field"
    if pydantic_error_type.endswith(("_type", "_parsing")):
        return "type"
    if pydantic_error_type in _RANGE_ERROR_TYPES:
        return "range"
    if pydantic_error_type in _UNSUPPORTED_ERROR_TYPES:
        return "unsupported"
    return "format"


def _escape_character(character: str) -> str:
    named = _NAMED_ESCAPES.get(character)
    if named is not None:
        return named
    if unicodedata.category(character) == "Cc":
        return f"\\x{ord(character):02x}"
    return character


def format_field_name_part(value: str) -> str:
    """項目名の 1 要素(入力に由来しうる)を、孤立サロゲートの置換・制御文字のエスケープ・
    100 文字への切り詰めの順で整える(ログの行の偽造と、JSON にできない文字を防ぐ)。

    切り詰めはエスケープの後に行い、エスケープ列(`\\n` など)の途中では切らない。
    """
    pieces: list[str] = []
    length = 0
    for character in _LONE_SURROGATE.sub(REPLACEMENT_CHARACTER, value):
        piece = _escape_character(character)
        if length + len(piece) > MAX_FIELD_NAME_CHARS:
            break
        pieces.append(piece)
        length += len(piece)
    return "".join(pieces)


def field_name_of(location: Sequence[Any]) -> str:
    """pydantic の `loc` から項目名を作る。例 `("body", "items", 0, "name")` → `items[0].name`。

    先頭の位置名(`body` など)は除く。何も残らなければ位置名そのものを使う(本文全体の
    欠落は `body`)。
    """
    parts = list(location)
    location_name = str(parts[0]) if parts and parts[0] in _LOCATION_NAMES else None
    if location_name is not None:
        parts = parts[1:]
    if not parts:
        return location_name or "request"

    field = ""
    for part in parts:
        if isinstance(part, int):
            field += f"[{part}]"
            continue
        separator = "." if field else ""
        field += separator + format_field_name_part(str(part))
    return field


def describe_validation_errors(errors: Sequence[Any]) -> list[dict[str, str]]:
    """pydantic の検証エラーを、項目名と `reason` だけにする。`input`・`ctx`・`msg` は使わない。"""
    return [
        {"field": field_name_of(error["loc"]), "reason": reason_of(error["type"])}
        for error in errors
    ]


async def _handle_api_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, ApiError)
    return error_response(
        error.status_code,
        error.code,
        error.message,
        retryable=error.retryable,
        details=error.details,
    )


async def _handle_validation_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    errors = error.errors()
    # 本文が JSON として読めないときは、項目の違反ではないので `details` を付けない。
    if any(item["type"] == "json_invalid" for item in errors):
        return error_response(400, "invalid_request", INVALID_REQUEST_MESSAGE)
    return error_response(
        400,
        "invalid_request",
        INVALID_REQUEST_MESSAGE,
        details={"errors": describe_validation_errors(errors)},
    )


async def _handle_http_exception(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StarletteHTTPException)
    code, message = _HTTP_ERRORS.get(error.status_code, _OTHER_HTTP_ERROR)
    # 405 の `Allow` など、例外が持つヘッダーは残す。
    headers = dict(error.headers) if error.headers else None
    return error_response(error.status_code, code, message, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
