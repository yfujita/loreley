"""EP-07・09・10 の DTO(B 4.2・5.1・5.2)。"""

from typing import Any

from loreley_api.admin.base.codes import (
    DeletionConfirmation,
    DeletionCurrentState,
    JobStatus,
    RegistrationPhase,
    RerunBlockedReason,
)
from loreley_api.admin.schemas.common import (
    JobBrief,
    PagedResponse,
    ResponseModel,
    Unavailable,
)


class CancelJobResponse(ResponseModel):
    """EP-07 の応答(B 4.2)。200 は `cancelled`(実行待ちを取り消した)、202 は `running`
    (実行中への取消要求の受付だけ。完了は EP-10 の `status` で確認する)。
    """

    job_id: str
    status: JobStatus


class JobListItem(JobBrief):
    """EP-09 の `items[]` の 1 行。`unavailable` は、この行の失敗(キーは `stalled`)。"""

    unavailable: Unavailable


class JobListResponse(PagedResponse[JobListItem]):
    pass


class Registration(ResponseModel):
    """登録の集計。保存値が読めない件数・`partial` は `null`。"""

    enumerated_count: int | None
    created_count: int | None
    updated_count: int | None
    unchanged_count: int | None
    skipped_count: int | None
    oversize_count: int | None
    error_count: int | None
    invalid_id_count: int | None
    partial: bool | None
    phase: RegistrationPhase | None


class DeletionSummary(ResponseModel):
    status: str | None
    reason: str | None
    forced: bool | None
    target_count: int | None
    denominator: int | None
    deleted_count: int | None
    enumerated_count: int | None
    n_seen: int | None
    e_missing: int | None
    finish_received_at: str | None
    deletion_started_at: str | None
    finished_at: str | None
    observed_at: str | None


class DeletionCurrent(ResponseModel):
    status: str | None
    reason: str | None
    reason_detail: str | None
    forced: bool | None
    target_count: int | None
    denominator: int | None
    deleted_count: int | None
    ended_at: str | None


class DeletionSettings(ResponseModel):
    ttl_seconds: int | None
    ratio_threshold_percent: int | float | None
    min_delete_count: int | None


class Deletion(ResponseModel):
    """`crawl` ジョブの削除の状況。`source_delete` ジョブでは、応答の `deletion` 自体が `null`。"""

    summary: DeletionSummary | None
    confirmation: DeletionConfirmation | None
    current: DeletionCurrent | None
    current_state: DeletionCurrentState
    # 現在値を読もうとした時刻(Admin API の時計)。読んでいなければ `null`。
    fetched_at: str | None
    settings: DeletionSettings | None


class JobDetailResponse(JobBrief):
    """EP-10。`JobBrief` の項目すべてに、詳細の項目を足す。"""

    failure_detail: str | None
    lease_expires_at: str | None
    latest_for_source: bool | None
    rerunnable: bool | None
    rerun_blocked_reason: RerunBlockedReason | None
    cancel_after_finish_notice: bool
    # コード名・項目は Crawler が定める(解釈せずそのまま通す)。
    warnings: list[dict[str, Any]]
    registration: Registration | None
    deletion: Deletion | None
    unavailable: Unavailable
