"""EP をまたぐ共通の DTO(B 2.11)。

`SourceSettings`・`JobAccepted`・`ExistingJob` は、それを返す EP(EP-02〜08)を実装するときに足す。
"""

from pydantic import BaseModel, ConfigDict

from loreley_api.admin.base.codes import (
    JobStatus,
    JobTrigger,
    JobType,
    UnavailableReason,
)

# 取得できなかった項目の「パス → 理由コード」(B 2.2)。常に存在し、失敗がなければ `{}`。
# 単一の応答の最上位は項目の正式なパス、一覧の行は行の中の相対パスがキー。
type Unavailable = dict[str, UnavailableReason]


class ResponseModel(BaseModel):
    """応答の DTO の基底。生成後は変更しない。"""

    model_config = ConfigDict(frozen=True)


class PagedResponse[ItemT](ResponseModel):
    """ページ付き応答(EP-09・11。B 2.1)。最上位の `unavailable` は、行に属さない項目だけ。"""

    items: list[ItemT]
    # 条件に合う総件数。窓(`window_limit`)を超えても正確。
    total: int
    page: int
    items_per_page: int
    window_limit: int
    unavailable: Unavailable


class JobBrief(ResponseModel):
    """ジョブの要約(EP-01・02・09・10)。自身は `unavailable` を持たない(外側の行が持つ)。"""

    job_id: str
    source_id: str
    job_type: JobType | None
    trigger: JobTrigger | None
    status: JobStatus | None
    force_delete: bool | None
    rewrite_mode: bool | None
    queued_at: str | None
    started_at: str | None
    finished_at: str | None
    failure_reason: str | None
    # `status=running` 以外は `false`。ロック文書を読めず判定できないときだけ `null`。
    stalled: bool | None
    cancellable: bool
