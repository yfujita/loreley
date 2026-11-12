"""検索インデックスの文書の組み立てと、変更の判定(arch 4.3、5章、`search-index-v0.9.md` 2.4)。

値のない項目は書かない(`None` を書かない)。`dynamic: strict` のため、定義にない項目は書かない
(`fetched_at`・`metadata`・`acl`・`extractor_version` は MVP では書かない)。
"""

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any

from loreley_indexer.common.timestamps import format_instant, parse_instant
from loreley_indexer.documents.document_id import normalize_external_id
from loreley_indexer.documents.extraction import ExtractedText, ExtractionResult
from loreley_indexer.documents.requests import DocumentInput
from loreley_indexer.documents.summarization import SummaryStatus

# (b) 変更なしの判定に使う項目。`last_seen_at`・`indexed_at`・要約の項目は比べない。
COMPARED_FIELDS = (
    "content_hash",
    "text_hash",
    "index_status",
    "title",
    "source_updated_at",
    "mime_type",
    "size",
    "url",
    "path",
)
_SUMMARY_FIELDS = ("summary", "summary_status", "summary_model")


class IndexStatus(StrEnum):
    INDEXED = "indexed"
    EXTRACT_FAILED = "extract_failed"


def build_source(
    *,
    document_id: str,
    source_id: str,
    document: DocumentInput,
    extraction: ExtractionResult,
    previous: Mapping[str, Any] | None,
    rewrite_mode: bool,
    summary_enabled: bool,
    crawl_started_at: datetime,
    indexed_at: datetime,
) -> dict[str, Any]:
    """全文書き込み(PUT)で書く文書全体を組み立てる。

    `previous` は読んだ既存の文書(新規なら None)。`last_seen_at` と、本文が同じときの
    要約の引き継ぎに使う。
    """
    source: dict[str, Any] = {
        "document_id": document_id,
        "source_id": source_id,
        "external_id": normalize_external_id(document.external_id),
        "title": document.title,
        "mime_type": document.mime_type,
        "size": document.size,
        "source_updated_at": format_instant(document.source_updated_at),
        "content_hash": document.content_hash,
        "indexed_at": format_instant(indexed_at),
        "last_seen_at": _later_of(previous, crawl_started_at),
    }
    if document.url is not None:
        source["url"] = document.url
    if document.path is not None:
        source["path"] = document.path

    if isinstance(extraction, ExtractedText):
        source["index_status"] = IndexStatus.INDEXED
        source["content"] = extraction.text
        source["text_hash"] = extraction.text_hash
        source["truncated"] = extraction.truncated
    else:
        # K30: 本文がないので `content`・`text_hash`・要約を書かず、旧い値も残さない。
        source["index_status"] = IndexStatus.EXTRACT_FAILED
        source["truncated"] = False

    source.update(
        _summary_fields(
            source=source,
            previous=previous,
            rewrite_mode=rewrite_mode,
            summary_enabled=summary_enabled,
        )
    )
    return source


def is_unchanged(previous: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    """(b) 原本ハッシュ・本文ハッシュ・処理状態・メタデータがすべて同じ。

    `extract_failed` は `text_hash` を持たず、双方に無ければ一致として扱う。
    """
    return all(previous.get(name) == candidate.get(name) for name in COMPARED_FIELDS)


def last_seen_at_is_behind(previous: Mapping[str, Any], crawl_started_at: datetime) -> bool:
    """既存の `last_seen_at` が `crawl_started_at` 未満(または読めない)なら True。

    保存値はミリ秒精度なので、`crawl_started_at` もミリ秒に揃えて比べる。そうしないと、
    マイクロ秒を持つ入力では、書いた直後でも毎回「古い」と判定して無駄な Update を送る。
    """
    last_seen_at = _parse_last_seen_at(previous)
    return last_seen_at is None or last_seen_at < _truncate_to_millis(crawl_started_at)


def _truncate_to_millis(instant: datetime) -> datetime:
    return parse_instant(format_instant(instant))


def _later_of(previous: Mapping[str, Any] | None, crawl_started_at: datetime) -> str:
    """読んだ値と `crawl_started_at` の大きい方。`last_seen_at` を古い値に戻さない(C-4)。"""
    last_seen_at = _parse_last_seen_at(previous) if previous is not None else None
    if last_seen_at is None:
        return format_instant(crawl_started_at)
    return format_instant(max(last_seen_at, crawl_started_at))


def _parse_last_seen_at(source: Mapping[str, Any]) -> datetime | None:
    value = source.get("last_seen_at")
    if not isinstance(value, str):
        return None
    try:
        return parse_instant(value)
    except ValueError:
        return None


def _summary_fields(
    *,
    source: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    rewrite_mode: bool,
    summary_enabled: bool,
) -> dict[str, Any]:
    """要約の項目。`summary` と `summary_model` は、引き継ぐときだけ書く。"""
    if source["index_status"] == IndexStatus.EXTRACT_FAILED:
        return {"summary_status": SummaryStatus.DISABLED}
    if previous is not None and not rewrite_mode and _body_is_unchanged(source, previous):
        carried = {name: previous[name] for name in _SUMMARY_FIELDS if name in previous}
        if "summary_status" in carried:
            return carried
    reset_status = SummaryStatus.PENDING if summary_enabled else SummaryStatus.DISABLED
    return {"summary_status": reset_status}


def _body_is_unchanged(source: Mapping[str, Any], previous: Mapping[str, Any]) -> bool:
    """`content_hash` と `text_hash` がともに既存と同じ(メタデータだけが変わった)。"""
    return all(source.get(name) == previous.get(name) for name in ("content_hash", "text_hash"))
