"""応答の解釈: 本文(JSON)から型付きの結果へ(module 4.9)。

契約と合わない応答(JSON でない、必須の項目がない、型が違う、未知の列挙値)は
`MalformedResponseError` にする。呼び出し側へは `IndexerRejected(MALFORMED_RESPONSE)` で伝わる
(Indexer の不整合。安全側に、リトライせずジョブを `failed` にできる)。
エラー応答(`error.code`)の読み取りも、ここで行う。例外のメッセージ・結果に、応答の値は入れない。
"""

import json
import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from loreley_crawler.infrastructure.indexer_client.results import (
    BatchResults,
    Change,
    CrawlStatus,
    DeletionRecordsDeleted,
    DiscardResult,
    DocumentFailed,
    DocumentRegistered,
    DocumentResult,
    DocumentsDeleted,
    FailureType,
    LastSeenEntry,
    LastSeenResult,
    LastSeenResults,
)

# 共通エラー形式の `error.code` として採用する形(`crawl_start_conflict` など)。外れる値は、
# 応答の本文が不正(あるいは別のシステムの応答)なので、ログや記録に入れない。
ERROR_CODE_PATTERN = re.compile(r"[a-z0-9_]{1,64}")


class MalformedResponseError(Exception):
    """応答が契約と合わない。メッセージに、応答の値を入れない。"""


def parse_error_code(data: bytes) -> str | None:
    """共通エラー形式 `{"error": {"code": ...}}` の `code`。読めない・形が合わなければ None。"""
    try:
        body = json.loads(data)
    except ValueError:  # UnicodeDecodeError・JSONDecodeError を含む
        return None
    error = body.get("error") if isinstance(body, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    if isinstance(code, str) and ERROR_CODE_PATTERN.fullmatch(code):
        return code
    return None


def parse_last_seen(data: bytes, expected_document_ids: Sequence[str]) -> LastSeenResults:
    """応答の `document_id` の並びが、要請の `document_ids` と一致しなければ不正とする。"""
    results = _list(_load_object(data), "results")
    entries = tuple(
        LastSeenEntry(
            document_id=_str(entry, "document_id"),
            result=_enum(LastSeenResult, _str(entry, "result")),
        )
        for entry in map(_as_object, results)
    )
    if [entry.document_id for entry in entries] != list(expected_document_ids):
        raise MalformedResponseError("the results do not match the requested documents")
    return LastSeenResults(entries=entries)


def parse_batch(data: bytes, expected_external_ids: Sequence[str]) -> BatchResults:
    """応答の `external_id` の並びが、要請の文書と一致しなければ不正とする。

    (`document_id` を Crawler の算出値と照合するのは、呼び出し側。architecture 7.11。)
    """
    results = _list(_load_object(data), "results")
    documents = tuple(_parse_document_result(_as_object(r)) for r in results)
    if [document.external_id for document in documents] != list(expected_external_ids):
        raise MalformedResponseError("the results do not match the requested documents")
    return BatchResults(documents=documents)


# Status API の削除結果の `status`(indexer-api 4.5。`running` 以外が終端状態)。`running` 以外を
# すべて終端とみなす(`confirmed` の根拠にする)ので、契約にない値(バージョン不整合・想定外の応答)
# は、終端とみなさず `MalformedResponseError` にする。
KNOWN_DELETION_STATUSES = frozenset(
    {"running", "deleted", "skipped_by_ratio", "validation_failed", "discarded", "failed"}
)


def parse_status(data: bytes) -> CrawlStatus:
    body = _load_object(data)
    status = _str(body, "status")
    if status not in KNOWN_DELETION_STATUSES:
        raise MalformedResponseError("an unknown deletion status")
    return CrawlStatus(
        crawl_id=_str(body, "crawl_id"),
        source_id=_str(body, "source_id"),
        status=status,
        reason=_optional_str(body, "reason"),
        forced=_optional_bool(body, "forced"),
        target_count=_optional_int(body, "target_count"),
        denominator=_optional_int(body, "denominator"),
        deleted_count=_optional_int(body, "deleted_count"),
        enumerated_count=_optional_int(body, "enumerated_count"),
        n_seen=_optional_int(body, "n_seen"),
        e_missing=_optional_int(body, "e_missing"),
        finish_received_at=_optional_str(body, "finish_received_at"),
        deletion_started_at=_optional_str(body, "deletion_started_at"),
        finished_at=_optional_str(body, "finished_at"),
        waiting_for=_optional_str(body, "waiting_for"),
    )


def parse_discard(data: bytes) -> DiscardResult:
    ids = _list(_load_object(data), "discarded_crawl_ids")
    if not all(isinstance(crawl_id, str) for crawl_id in ids):
        raise MalformedResponseError("discarded_crawl_ids must be strings")
    return DiscardResult(discarded_crawl_ids=tuple(ids))


def parse_documents_deleted(data: bytes) -> DocumentsDeleted:
    return DocumentsDeleted(deleted_count=_int(_load_object(data), "deleted_count"))


def parse_deletion_records_deleted(data: bytes) -> DeletionRecordsDeleted:
    return DeletionRecordsDeleted(deleted=_bool(_load_object(data), "deleted"))


def _parse_document_result(entry: dict[str, Any]) -> DocumentResult:
    external_id = _str(entry, "external_id")
    document_id = _str(entry, "document_id")
    status = _str(entry, "status")
    if status == "ok":
        return DocumentRegistered(
            external_id=external_id,
            document_id=document_id,
            change=_enum(Change, _str(entry, "change")),
            extract_failed=_bool(entry, "extract_failed"),
        )
    if status == "failed":
        return DocumentFailed(
            external_id=external_id,
            document_id=document_id,
            failure_type=_enum(FailureType, _str(entry, "failure_type")),
        )
    raise MalformedResponseError("unknown document status")


def _load_object(data: bytes) -> dict[str, Any]:
    try:
        return _as_object(json.loads(data))
    except ValueError:  # UnicodeDecodeError・JSONDecodeError を含む
        raise MalformedResponseError("the response is not JSON") from None


def _as_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MalformedResponseError("an object is expected")
    return value


def _list(body: dict[str, Any], name: str) -> list[Any]:
    value = body.get(name)
    if not isinstance(value, list):
        raise MalformedResponseError(f"{name} must be a list")
    return value


def _str(body: dict[str, Any], name: str) -> str:
    value = body.get(name)
    if not isinstance(value, str):
        raise MalformedResponseError(f"{name} must be a string")
    return value


def _int(body: dict[str, Any], name: str) -> int:
    value = body.get(name)
    if type(value) is not int:
        raise MalformedResponseError(f"{name} must be an integer")
    return value


def _bool(body: dict[str, Any], name: str) -> bool:
    value = body.get(name)
    if type(value) is not bool:
        raise MalformedResponseError(f"{name} must be a boolean")
    return value


# 値のない項目は、キーごと省かれる(null も同じ扱い)。
def _optional_str(body: dict[str, Any], name: str) -> str | None:
    return _str(body, name) if body.get(name) is not None else None


def _optional_int(body: dict[str, Any], name: str) -> int | None:
    return _int(body, name) if body.get(name) is not None else None


def _optional_bool(body: dict[str, Any], name: str) -> bool | None:
    return _bool(body, name) if body.get(name) is not None else None


def _enum[EnumT: StrEnum](enum_class: type[EnumT], value: str) -> EnumT:
    try:
        return enum_class(value)
    except ValueError:
        raise MalformedResponseError("an unknown value") from None
