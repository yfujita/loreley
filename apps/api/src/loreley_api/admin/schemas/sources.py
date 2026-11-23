"""EP-01・02 の DTO(B 3.1・3.2)。"""

from loreley_api.admin.base.codes import LockState, SourceStatus
from loreley_api.admin.schemas.common import (
    ExistingJob,
    JobBrief,
    ResponseModel,
    SourceSettings,
    Unavailable,
)


class SourceListItem(ResponseModel):
    """EP-01 の `items[]` の 1 行。`unavailable` は、この行の失敗(キーは行の中の相対パス)。"""

    source_id: str
    connector_type: str | None
    schedule_cron: str | None
    status: SourceStatus | None
    last_crawl: JobBrief | None
    last_completed_at: str | None
    # `status=deleting` のときだけ値がある。
    delete_job: JobBrief | None
    document_count: int | None
    unavailable: Unavailable


class SourceListResponse(ResponseModel):
    """EP-01。全件を返す。最上位の `unavailable` は常に `{}`(行に属さない項目がない)。"""

    items: list[SourceListItem]
    unavailable: Unavailable


class Lock(ResponseModel):
    state: LockState
    # ロックなし・`job_id` が読めないときは `null`。
    job: ExistingJob | None
    acquired_at: str | None


class IndexSummary(ResponseModel):
    document_count: int | None


class SourceDetailResponse(SourceSettings):
    """EP-02。`SourceSettings` の項目すべてに、ロック・直近のジョブ・登録文書数を足す。"""

    # 取得できなかったときは `null`(`unavailable.lock`)。
    lock: Lock | None
    last_crawl: JobBrief | None
    last_completed_at: str | None
    delete_job: JobBrief | None
    index: IndexSummary
    unavailable: Unavailable
