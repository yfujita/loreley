"""リクエスト本文の読み取りと上限(A 5.1)。

本文の上限は 1 MiB(仮値)。超過は 400 `invalid_request`(`details` なし)。
`Content-Length` が上限を超えるときは本文を読まずに拒否し、ないとき(chunked)や偽りのときは、
読みながら数えて上限を超えた時点で打ち切る。
"""

from fastapi import Request

from loreley_api.common.http.errors import INVALID_REQUEST_MESSAGE, ApiError

MAX_REQUEST_BODY_BYTES = 1024 * 1024

# これより桁数が多い `Content-Length` は、数値にせず上限超過とみなす。Python の `int()` は
# 4,300 桁超で `ValueError` になり、500 になってしまうため。実在しうる長さ(2^63 未満)は
# 19 桁に収まる。
_MAX_DECLARED_LENGTH_DIGITS = 19


def _too_large() -> ApiError:
    return ApiError(400, "invalid_request", INVALID_REQUEST_MESSAGE)


def _declares_more_than(declared_length: str, max_bytes: int) -> bool:
    """`Content-Length` が数字だけで、`max_bytes` を超える長さを宣言しているか。"""
    if not (declared_length.isascii() and declared_length.isdigit()):
        return False
    significant_digits = declared_length.lstrip("0")
    if len(significant_digits) > _MAX_DECLARED_LENGTH_DIGITS:
        return True
    return int(significant_digits or "0") > max_bytes


async def read_limited_body(request: Request, *, max_bytes: int = MAX_REQUEST_BODY_BYTES) -> bytes:
    if _declares_more_than(request.headers.get("content-length", ""), max_bytes):
        raise _too_large()

    chunks: list[bytes] = []
    received_bytes = 0
    async for chunk in request.stream():
        received_bytes += len(chunk)
        if received_bytes > max_bytes:
            raise _too_large()
        chunks.append(chunk)
    return b"".join(chunks)
