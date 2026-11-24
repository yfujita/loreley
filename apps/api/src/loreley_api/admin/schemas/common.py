"""EP をまたぐ共通の DTO(B 2.11)。"""

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


class RequestModel(BaseModel):
    """リクエスト本文の DTO の基底。

    型は厳密(文字列から数値・真偽値へ変換しない。`30.0` は整数でない)で、未知の項目は拒否する
    (`unknown_field`。A 5.1・B 2.12)。
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


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


class StoredSourceSettings(ResponseModel):
    """保存値を読んだデータソースの設定(EP-02 の応答の土台)。

    保存値を読むので、読めない項目(欠落・型違い)は `null` で、`unavailable.<項目名>` に
    `malformed` が載る(B 2.2)。`ttl_days` は `ttl_seconds` が日で割り切れるときだけ。
    EP-03・04 の応答は、Crawler が返した値を確かめて作るので、`null` を持たない `SourceSettings`。
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


class SourceSettings(ResponseModel):
    """登録・更新が返すデータソースの設定(EP-03・04。B 2.11)。

    Crawler が返した保存内容を確かめてから作る(読めなければ 502 で、この型にならない)ので、
    `null` を許すのは `ttl_days`(日で割り切れないとき)と `schedule_cron`(手動のみ)だけ。
    """

    source_id: str
    connector_type: str
    connector_config: dict[str, Any]
    ttl_seconds: int
    ttl_days: int | None
    ratio_threshold_percent: int | float
    min_delete_count: int
    schedule_cron: str | None
    status: SourceStatus
    updated_at: str


class JobAccepted(ResponseModel):
    """受け付けたジョブ(EP-05・06 の 202)。"""

    job_id: str
    job_type: JobType
    source_id: str
    status: JobStatus
    trigger: JobTrigger
    # 記録した指定。`source_delete` は Crawler の応答に含まれないので `null`。
    force_delete: bool | None
    rewrite_mode: bool | None
    queued_at: str


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
