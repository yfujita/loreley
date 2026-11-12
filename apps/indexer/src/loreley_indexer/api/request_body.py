"""リクエストボディの読み込みと、JSON・形式の検証(api 3.4、plan 案22)。

ボディのサイズは、`Content-Length` を先に見て、読む前に拒否する(`max_request_body_bytes`)。
`Content-Length` のない送信(チャンク)でも、読んだ量が上限を超えた時点で止める。
超過は 413 ではなく 400 `invalid_request`(契約に規定がなく、形式不正として扱う)。
"""

import json
from typing import Any, NoReturn

from fastapi import Request
from pydantic import BaseModel, ValidationError
from starlette.requests import ClientDisconnect

from loreley_indexer.api.errors import InvalidRequestError
from loreley_indexer.api.schemas import describe_validation_error

BODY_TOO_LARGE = "the request body is too large"
BODY_NOT_JSON = "the request body is not valid JSON"
BODY_INCOMPLETE = "the request body was not fully received"
# 2**64 は 20 桁。これを超える長さは、どの上限設定よりも大きい。
MAX_CONTENT_LENGTH_DIGITS = 20


async def read_limited_body(request: Request, *, max_bytes: int) -> bytes:
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        if not declared_length.isascii() or not declared_length.isdigit():
            raise InvalidRequestError("the Content-Length header is invalid")
        # 桁数が極端に多いと `int()` が ValueError になる(Python の桁数制限)ので、先に弾く。
        if len(declared_length) > MAX_CONTENT_LENGTH_DIGITS or int(declared_length) > max_bytes:
            raise InvalidRequestError(BODY_TOO_LARGE)
    chunks: list[bytes] = []
    total_bytes = 0
    try:
        async for chunk in request.stream():
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                raise InvalidRequestError(BODY_TOO_LARGE)
            chunks.append(chunk)
    except ClientDisconnect:
        # 送信途中の切断はクライアント側の事情で、サーバの異常ではない(ERROR にしない)。
        # 応答は誰にも届かないので、形式不正の 400 として扱う。
        raise InvalidRequestError(BODY_INCOMPLETE) from None
    return b"".join(chunks)


def parse_json(body: bytes) -> Any:
    """UTF-8 の JSON をパースする。`NaN`・`Infinity` は JSON ではないので拒否する。

    孤立サロゲート(`\\ud800`)は、ここでは通す(`title` などは文書単位でドメインが拒否する)。
    ほかの文字列の項目は、`schemas` の検証が拒否する。
    """
    try:
        return json.loads(body.decode("utf-8"), parse_constant=_reject_constant)
    except (ValueError, RecursionError):  # UnicodeDecodeError・JSONDecodeError は ValueError
        raise InvalidRequestError(BODY_NOT_JSON) from None


def parse_model[ModelT: BaseModel](model_class: type[ModelT], body: bytes) -> ModelT:
    """ボディを JSON として読み、strict で検証する。不正なら位置と型だけの 400。"""
    payload = parse_json(body)
    try:
        return model_class.model_validate(payload, strict=True)
    except ValidationError as error:
        raise InvalidRequestError(describe_validation_error(error)) from None


def _reject_constant(_name: str) -> NoReturn:
    raise ValueError("not a JSON constant")
