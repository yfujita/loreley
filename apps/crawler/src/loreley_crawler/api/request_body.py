"""リクエスト本文の読み込みと大きさの上限(crawler-api 3.2。CAPI-P-28)。

上限は 10 MiB(仮値。ユーザー指示 2026-11-16。設定にはしない)。`Content-Length` を先に見て、読む
前に拒否する。`Content-Length` のない送信(チャンク)でも、読んだ量が上限を超えた時点で止める。
超過は 413 ではなく、JSON として読めない本文と同じ 400 `invalid_request`(`details` なし。
Indexer API の本文の上限の扱いと同じ)。
"""

from fastapi import Request
from starlette.requests import ClientDisconnect

from loreley_crawler.api.errors import InvalidRequestError

MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024
# 2**64 は 20 桁。これを超える長さは上限より必ず大きい(`int()` の桁数制限を避けるためにも先に見る)。
_MAX_CONTENT_LENGTH_DIGITS = 20


async def read_limited_body(request: Request, *, max_bytes: int = MAX_REQUEST_BODY_BYTES) -> bytes:
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        if not declared_length.isascii() or not declared_length.isdigit():
            raise InvalidRequestError()
        if len(declared_length) > _MAX_CONTENT_LENGTH_DIGITS or int(declared_length) > max_bytes:
            raise InvalidRequestError()
    chunks: list[bytes] = []
    total_bytes = 0
    try:
        async for chunk in request.stream():
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                raise InvalidRequestError()
            chunks.append(chunk)
    except ClientDisconnect:
        # 送信途中の切断はクライアント側の事情で、サーバの異常ではない。応答は誰にも届かない。
        raise InvalidRequestError() from None
    return b"".join(chunks)
