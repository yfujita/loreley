"""リクエストの組み立て: パスと JSON の本文(module 4.9。architecture 7.2・7.4・7.10。CM-K-6)。

JSON は厳密な型で作る(型を変換しない。`NaN`・`Infinity` を送らない)。
- 数値・真偽値は、渡された型のまま送る。`ttl`・`min_delete_count` は整数、`ratio_threshold` は
  有限の数値、`force_delete`・`rewrite_mode` は真偽値で、型が違えば(`bool` を整数として渡すなど)
  送る前に `TypeError` にする(`"true"` や `1` に変換して送ると、Indexer が 400 にするか、
  再送で値が変わって 409 になる)。範囲は検証しない(Indexer も検証しない。CA-K-16)。
- 日時は `common.timestamps.format_instant`(UTC・ミリ秒)の文字列にする。同じ日時は常に同じ
  文字列になるので、再送でも同一の値を送れる。
- `raw_content` は標準の base64(パディングあり・改行なし)。
- `source_id`・`crawl_id` は、パスにパーセントエンコードして入れる(`/` なども全て)。

ID・`content_hash` の検証と算出はここでは行わない(`documents` と、登録時の検証が担う)。
`json.dumps` は `ensure_ascii` の既定のまま使う。孤立サロゲートを含む `title` などは `\\ud800` の
エスケープになり、Indexer が文書単位で拒否する(UTF-8 に直そうとして例外にならない)。
"""

import base64
import json
import math
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from urllib.parse import quote

from loreley_crawler.common.timestamps import format_instant
from loreley_crawler.infrastructure.indexer_client.models import (
    DocumentToRegister,
    FinishOutcome,
    LockInfo,
)


def encode_json(payload: dict[str, Any]) -> bytes:
    """JSON の本文。`NaN`・`Infinity` は `ValueError`(JSON にない定数を送らない)。"""
    return json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("ascii")


def quote_path_segment(value: str) -> str:
    return quote(value, safe="")


def start_path() -> str:
    return "/crawls/start"


def finish_path(crawl_id: str) -> str:
    return f"/crawls/{quote_path_segment(crawl_id)}/finish"


def status_path(crawl_id: str) -> str:
    return f"/crawls/{quote_path_segment(crawl_id)}"


def batch_path(source_id: str) -> str:
    return f"/sources/{quote_path_segment(source_id)}/documents:batch"


def last_seen_path(source_id: str) -> str:
    return f"/sources/{quote_path_segment(source_id)}/last-seen"


def discard_path(source_id: str) -> str:
    return f"/sources/{quote_path_segment(source_id)}/deletions:discard"


def delete_documents_path(source_id: str) -> str:
    return f"/sources/{quote_path_segment(source_id)}/documents"


def delete_deletion_records_path(source_id: str) -> str:
    return f"/sources/{quote_path_segment(source_id)}/deletion-records"


def lock_payload(lock: LockInfo) -> dict[str, str]:
    return {"owner": lock.owner, "job_id": lock.job_id}


def start_payload(
    *,
    crawl_id: str,
    source_id: str,
    crawl_started_at: datetime,
    ttl: int,
    ratio_threshold: float,
    min_delete_count: int,
    force_delete: bool,
    rewrite_mode: bool,
) -> dict[str, Any]:
    """開始通知(indexer-api 4.1)。`rewrite_mode` は省略せず、常に真偽値で送る(architecture 7.4)。"""
    _require_int("ttl", ttl)
    _require_finite_number("ratio_threshold", ratio_threshold)
    _require_int("min_delete_count", min_delete_count)
    _require_bool("force_delete", force_delete)
    _require_bool("rewrite_mode", rewrite_mode)
    return {
        "crawl_id": crawl_id,
        "source_id": source_id,
        "crawl_started_at": format_instant(crawl_started_at),
        "ttl": ttl,
        "ratio_threshold": ratio_threshold,
        "min_delete_count": min_delete_count,
        "force_delete": force_delete,
        "rewrite_mode": rewrite_mode,
    }


def last_seen_payload(
    *,
    crawl_id: str,
    crawl_started_at: datetime,
    lock: LockInfo,
    document_ids: Sequence[str],
) -> dict[str, Any]:
    """`last-seen`(indexer-api 4.2)。件数の分割(上限以下)は呼び出し側。"""
    return {
        "crawl_id": crawl_id,
        "lock": lock_payload(lock),
        "crawl_started_at": format_instant(crawl_started_at),
        "document_ids": list(document_ids),
    }


def batch_payload(
    *,
    crawl_id: str,
    crawl_started_at: datetime,
    lock: LockInfo,
    documents: Sequence[DocumentToRegister],
) -> dict[str, Any]:
    """バッチ登録(indexer-api 4.3)。`documents` が空なら(Indexer が 400 にする)`ValueError`。"""
    if not documents:
        raise ValueError("documents must not be empty")
    return {
        "crawl_id": crawl_id,
        "crawl_started_at": format_instant(crawl_started_at),
        "lock": lock_payload(lock),
        "documents": [_document_payload(document) for document in documents],
    }


def finish_payload(
    *,
    source_id: str,
    outcome: FinishOutcome,
    finished_at: datetime,
    enumerated_count: int | None,
    skipped_document_ids: Sequence[str] | None,
    oversize_document_ids: Sequence[str] | None,
) -> dict[str, Any]:
    """終了通知(indexer-api 4.4)。

    `enumeration_completed` では件数と 2 つの ID 一覧が必須。`failed`・`cancelled` では省略でき
    (architecture 7.5)、渡された項目だけを送る。`skipped_count`(任意)は送らない。
    """
    counts_given = (enumerated_count, skipped_document_ids, oversize_document_ids)
    if outcome == FinishOutcome.ENUMERATION_COMPLETED and None in counts_given:
        raise ValueError("enumeration_completed requires the count and both id lists")
    payload: dict[str, Any] = {
        "source_id": source_id,
        "outcome": outcome.value,
        "finished_at": format_instant(finished_at),
    }
    if enumerated_count is not None:
        _require_int("enumerated_count", enumerated_count)
        payload["enumerated_count"] = enumerated_count
    if skipped_document_ids is not None:
        payload["skipped_document_ids"] = list(skipped_document_ids)
    if oversize_document_ids is not None:
        payload["oversize_document_ids"] = list(oversize_document_ids)
    return payload


def locked_payload(lock: LockInfo) -> dict[str, Any]:
    """ソース削除 2・3(`DELETE`)のボディ。ソース削除 1 は、これに `reason` を足す。"""
    return {"lock": lock_payload(lock)}


def discard_payload(lock: LockInfo) -> dict[str, Any]:
    return {**locked_payload(lock), "reason": "source_deleted"}


def _document_payload(document: DocumentToRegister) -> dict[str, Any]:
    _require_int("size", document.size)
    payload: dict[str, Any] = {
        "external_id": document.external_id,
        "title": document.title,
        "mime_type": document.mime_type,
        "raw_content": base64.b64encode(document.raw_content).decode("ascii"),
        "content_hash": document.content_hash,
        "source_updated_at": format_instant(document.source_updated_at),
        "size": document.size,
    }
    if document.url is not None:
        payload["url"] = document.url
    if document.path is not None:
        payload["path"] = document.path
    return payload


def _require_int(name: str, value: object) -> None:
    # `bool` は `int` の子クラスだが、JSON では `true` になる。整数として送らない。
    if type(value) is not int:
        raise TypeError(f"{name} must be an int")


def _require_bool(name: str, value: object) -> None:
    if type(value) is not bool:
        raise TypeError(f"{name} must be a bool")


def _require_finite_number(name: str, value: float) -> None:
    if type(value) not in (int, float):
        raise TypeError(f"{name} must be a number")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
