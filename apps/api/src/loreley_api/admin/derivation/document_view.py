"""EP-11 の各タブの行の元(C 3.3 R-10。B 6.1)。

保存値の型が違う・許される値にないときは、読めない値として `None` にする(未知の値を通さない。
C 5.0)。`document_id` は、`loreley-jobs` の記録(`skipped`・`oversize`)では `_source` の項目、
検索インデックスの文書(`extract_failed`・`summary_pending`)では文書の `_id`。
"""

from dataclasses import dataclass

from loreley_api.admin.base.codes import OversizeDetector, SkipStage
from loreley_api.admin.derivation.values import (
    Document,
    read_choice,
    read_instant_text,
    read_int,
    read_non_empty_str,
    read_str,
)


@dataclass(frozen=True)
class SkippedView:
    # 読めないとき `None`(`existence` は `unknown`)。
    document_id: str | None
    external_id: str | None
    stage: SkipStage | None
    # 記録のまま「分類名: 固定文」。分解は画面が行う。
    reason: str | None
    attempts: int | None
    consecutive_skips: int | None
    first_skipped_at: str | None
    last_skipped_at: str | None
    last_job_id: str | None


@dataclass(frozen=True)
class ExtractFailedView:
    document_id: str
    title: str | None
    external_id: str | None
    mime_type: str | None
    size: int | None
    source_updated_at: str | None
    last_seen_at: str | None


@dataclass(frozen=True)
class OversizeView:
    document_id: str | None
    external_id: str | None
    detected_by: OversizeDetector | None
    # 分かる場合だけ。なければ `None`。
    size: int | None
    first_detected_at: str | None
    last_detected_at: str | None
    last_job_id: str | None


@dataclass(frozen=True)
class SummaryPendingView:
    document_id: str
    title: str | None
    external_id: str | None
    mime_type: str | None
    source_updated_at: str | None
    indexed_at: str | None


def read_skipped(source: Document) -> SkippedView:
    return SkippedView(
        document_id=read_non_empty_str(source.get("document_id")),
        external_id=read_str(source.get("external_id")),
        stage=read_choice(source.get("stage"), SkipStage),
        reason=read_str(source.get("reason")),
        attempts=read_int(source.get("attempts")),
        consecutive_skips=read_int(source.get("consecutive_skips")),
        first_skipped_at=read_instant_text(source.get("first_skipped_at")),
        last_skipped_at=read_instant_text(source.get("last_skipped_at")),
        last_job_id=read_str(source.get("last_job_id")),
    )


def read_extract_failed(record_id: str, source: Document) -> ExtractFailedView:
    return ExtractFailedView(
        document_id=record_id,
        title=read_str(source.get("title")),
        external_id=read_str(source.get("external_id")),
        mime_type=read_str(source.get("mime_type")),
        size=read_int(source.get("size")),
        source_updated_at=read_instant_text(source.get("source_updated_at")),
        last_seen_at=read_instant_text(source.get("last_seen_at")),
    )


def read_oversize(source: Document) -> OversizeView:
    return OversizeView(
        document_id=read_non_empty_str(source.get("document_id")),
        external_id=read_str(source.get("external_id")),
        detected_by=read_choice(source.get("detected_by"), OversizeDetector),
        size=read_int(source.get("size")),
        first_detected_at=read_instant_text(source.get("first_detected_at")),
        last_detected_at=read_instant_text(source.get("last_detected_at")),
        last_job_id=read_str(source.get("last_job_id")),
    )


def read_summary_pending(record_id: str, source: Document) -> SummaryPendingView:
    return SummaryPendingView(
        document_id=record_id,
        title=read_str(source.get("title")),
        external_id=read_str(source.get("external_id")),
        mime_type=read_str(source.get("mime_type")),
        source_updated_at=read_instant_text(source.get("source_updated_at")),
        indexed_at=read_instant_text(source.get("indexed_at")),
    )
