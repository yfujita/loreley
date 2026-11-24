"""Crawler の応答の解釈(B 9.1。C 4.1・4.2。D 4.9)。

- 本文は 2 MiB まで読む(超えたら契約外。C 4.1 は 1 MiB。リクエスト本文の上限 1 MiB の設定を
  Crawler が足して返す登録・更新の応答を、502 にしないため広げた)。
- 3xx(リダイレクトは追従しない)・その API の成功のステータス以外の 2xx・JSON のオブジェクトでない
  本文・`error.code` がないエラー本文は、契約外(502 の元)。
- エラーでは `error.code` と `details` だけを取り出す。`message` は `config_invalid` のときだけ読む
  (入力値を含みうるため。B 9.1)。

ここは純粋な関数で、urllib3 を使わない(`http_client.py` が応答を渡す)。
"""

import json
from collections.abc import Iterable
from typing import Any, NoReturn

from loreley_api.infrastructure.crawler_client import config_invalid
from loreley_api.infrastructure.crawler_client.client import (
    CrawlerContractViolation,
    CrawlerRejected,
    CrawlerReply,
    CrawlerSucceeded,
)

CONFIG_INVALID_CODE = "config_invalid"
# `admin.base.constants.CRAWLER_RESPONSE_MAX_BYTES` と同じ値(infrastructure は admin を import
# できないので、ここにも持つ。理由もそちらを参照)。
RESPONSE_MAX_BYTES = 2 * 1024 * 1024


def collect_within_limit(chunks: Iterable[bytes], max_bytes: int) -> bytes | None:
    """本文を集める。`max_bytes` を超えた時点で読むのをやめて `None`。"""
    collected: list[bytes] = []
    received_bytes = 0
    for chunk in chunks:
        received_bytes += len(chunk)
        if received_bytes > max_bytes:
            return None
        collected.append(chunk)
    return b"".join(collected)


def interpret_response(
    status: int, body: bytes, *, success_statuses: frozenset[int]
) -> CrawlerReply:
    if 300 <= status < 400:
        return CrawlerContractViolation("redirect", status)
    if status >= 400:
        return _interpret_error(status, body)
    if status not in success_statuses:
        return CrawlerContractViolation("unexpected_status", status)
    parsed = _parse_json_object(body)
    if parsed is None:
        return CrawlerContractViolation("malformed_body", status)
    return CrawlerSucceeded(status=status, body=parsed)


def _interpret_error(status: int, body: bytes) -> CrawlerReply:
    malformed = CrawlerContractViolation("malformed_error", status)
    parsed = _parse_json_object(body)
    error = parsed.get("error") if parsed is not None else None
    if not isinstance(error, dict):
        return malformed
    code = error.get("code")
    if not isinstance(code, str) or not code:
        return malformed
    details = error.get("details")
    rejected_details = details if isinstance(details, dict) else None
    if code != CONFIG_INVALID_CODE:
        return CrawlerRejected(status, code, rejected_details, config_invalid=None)
    message = error.get("message")
    if not isinstance(message, str):
        return malformed
    return CrawlerRejected(
        status, code, rejected_details, config_invalid=config_invalid.describe(message)
    )


def _parse_json_object(body: bytes) -> dict[str, Any] | None:
    try:
        parsed = json.loads(body.decode("utf-8"), parse_constant=_reject_constant)
    except (ValueError, RecursionError):  # UnicodeDecodeError・JSONDecodeError は ValueError
        return None
    return parsed if isinstance(parsed, dict) else None


def _reject_constant(name: str) -> NoReturn:
    """`NaN`・`Infinity` は JSON ではない。通すと、応答の再出力で壊れる。"""
    raise ValueError(f"unsupported JSON constant: {name}")
