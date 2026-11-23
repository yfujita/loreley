"""リクエスト本文の読み取りと上限(A 5.1)。

本文の上限は 1 MiB(仮値)。超過は 400 `invalid_request`(`details` なし)。
`Content-Length` が上限を超えるときは本文を読まずに拒否し、ないとき(chunked)や偽りのときは、
読みながら数えて上限を超えた時点で打ち切る。
"""

from fastapi import Request

from loreley_api.common.http.errors import INVALID_REQUEST_MESSAGE, ApiError

MAX_REQUEST_BODY_BYTES = 1024 * 1024


def _too_large() -> ApiError:
    return ApiError(400, "invalid_request", INVALID_REQUEST_MESSAGE)


async def read_limited_body(request: Request, *, max_bytes: int = MAX_REQUEST_BODY_BYTES) -> bytes:
    declared_length = request.headers.get("content-length", "")
    if declared_length.isascii() and declared_length.isdigit() and int(declared_length) > max_bytes:
        raise _too_large()

    chunks: list[bytes] = []
    received_bytes = 0
    async for chunk in request.stream():
        received_bytes += len(chunk)
        if received_bytes > max_bytes:
            raise _too_large()
        chunks.append(chunk)
    return b"".join(chunks)
