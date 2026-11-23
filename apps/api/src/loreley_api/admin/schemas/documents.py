"""EP-11 の DTO(B 6.1)。タブごとに行の項目が違う。どのタブの行も `unavailable` を持つ。"""

from loreley_api.admin.base.codes import (
    DocumentExistence,
    DocumentTab,
    OversizeDetector,
    SkipStage,
)
from loreley_api.admin.schemas.common import PagedResponse, ResponseModel, Unavailable


class SkippedDocument(ResponseModel):
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
    existence: DocumentExistence
    # キーは `existence` だけ。
    unavailable: Unavailable


class ExtractFailedDocument(ResponseModel):
    document_id: str
    title: str | None
    external_id: str | None
    mime_type: str | None
    size: int | None
    source_updated_at: str | None
    last_seen_at: str | None
    unavailable: Unavailable


class OversizeDocument(ResponseModel):
    document_id: str | None
    external_id: str | None
    detected_by: OversizeDetector | None
    size: int | None
    first_detected_at: str | None
    last_detected_at: str | None
    last_job_id: str | None
    unavailable: Unavailable


class SummaryPendingDocument(ResponseModel):
    document_id: str
    title: str | None
    external_id: str | None
    mime_type: str | None
    source_updated_at: str | None
    indexed_at: str | None
    unavailable: Unavailable


DocumentRow = SkippedDocument | ExtractFailedDocument | OversizeDocument | SummaryPendingDocument


class TabCounts(ResponseModel):
    """各タブの総件数。取得できなかったタブは `null`(最上位の `unavailable.tab_counts.<タブ>`)。"""

    skipped: int | None
    extract_failed: int | None
    oversize: int | None
    summary_pending: int | None


class DocumentListResponse(PagedResponse[DocumentRow]):
    """EP-11。最上位の `unavailable` は、行に属さない項目(`tab_counts.<タブ>` など)だけ。"""

    tab: DocumentTab
    tab_counts: TabCounts
    # 登録文書数(`index_status` を問わない)。取得できなかったときは `null`。
    document_count: int | None
