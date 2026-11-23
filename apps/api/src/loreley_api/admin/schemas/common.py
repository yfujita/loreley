"""EP をまたぐ共通の DTO(B 2.11)。

`JobAccepted` は、それを返す EP(EP-05・06)を実装するときに足す。
"""

from typing import Any

from pydantic import BaseModel, ConfigDict

from loreley_api.admin.base.codes import (
    JobStatus,
    JobTrigger,
    JobType,
    SourceStatus,
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


class SourceSettings(ResponseModel):
    """データソースの設定(EP-02〜04)。

    EP-02 は保存値を読むので、読めない項目(欠落・型違い)は `null` で、`unavailable.<項目名>` に
    `malformed` が載る(B 2.2)。`ttl_days` は `ttl_seconds` が日で割り切れるときだけ。
    """

    source_id: str
    connector_type: str | None
    # 保存済みの値をそのまま返す(補完・加工しない)。
    connector_config: dict[str, Any] | None
    ttl_seconds: int | None
    ttl_days: int | None
    ratio_threshold_percent: int | float | None
    min_delete_count: int | None
    # `null` は手動のみ。
    schedule_cron: str | None
    status: SourceStatus | None
    updated_at: str | None


class ExistingJob(ResponseModel):
    """ロック文書が指すジョブ(`lock.job`、409 の `details.existing_job`)。

    ジョブ記録がない(孤児ロック)・値が読めないときは `null`。
    """

    job_id: str
    job_type: JobType | None
    status: JobStatus | None
    trigger: JobTrigger | None
    # ロック文書のリース期限。実行待ちや読めない値は `null`。
    lease_expires_at: str | None
