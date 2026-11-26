"""EP-01〜06・08 の DTO(B 3章・4.1・4.3)。EP-07 は `jobs.py`。"""

from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_core import PydanticCustomError

from loreley_api.admin.base.codes import LockState, SourceStatus
from loreley_api.admin.base.constants import SOURCE_ID_PATTERN
from loreley_api.admin.schemas.common import (
    ExistingJob,
    JobBrief,
    RequestModel,
    ResponseModel,
    StoredSourceSettings,
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


class SourceDetailResponse(StoredSourceSettings):
    """EP-02。`StoredSourceSettings` の項目すべてに、ロック・直近のジョブ・登録文書数を足す。"""

    # 取得できなかったときは `null`(`unavailable.lock`)。
    lock: Lock | None
    last_crawl: JobBrief | None
    last_completed_at: str | None
    delete_job: JobBrief | None
    index: IndexSummary
    unavailable: Unavailable


# 省略は「指定なし」、`null` は 400 `type`(下の `_reject_explicit_null`)なので、OpenAPI では
# 「任意かつ非 null の整数」にする(`int | None` のままだと、型生成が null を送れる型にする)。
def _non_null_integer_schema(schema: dict[str, Any]) -> None:
    # 既定値 `null` も外す(非 null の型に `default: null` が残ると、型と食い違う)。
    schema.pop("anyOf", None)
    schema.pop("default", None)
    schema["type"] = "integer"


OptionalTtl = Annotated[int | None, Field(json_schema_extra=_non_null_integer_schema)]


class UpdateSourceBody(RequestModel):
    """EP-04 の本文。EP-03 の本文から `source_id`・`connector_type` を除いたもの(全置換)。

    ここで検証するのは形(型・必須・未知の項目)だけ。`ttl_days` と `ttl_seconds` の排他・必須と、
    値の範囲・桁は、換算と一緒に `services` が検証する(B 2.4。範囲の違反は、形の違反がないときに
    すべて返す)。`connector_config` の中身と `schedule_cron` の書式は検証しない(Crawler に任せる)。
    """

    # JSON のオブジェクトであることだけを確かめる(中身は中継する)。
    connector_config: dict[str, Any]
    # どちらか一方が必須(両方・どちらもなしは `services` が `exclusive`・`required`)。
    ttl_days: OptionalTtl = None
    ttl_seconds: OptionalTtl = None
    # 整数も受ける(strict の `float` は整数を受け、`int | float` は違反の項目名に型名が付くため)。
    # 範囲内(0 以上 100 未満)の整数は `float` でも正確。
    ratio_threshold_percent: float
    min_delete_count: int
    # 省略・`null` は手動のみ。
    schedule_cron: str | None = None

    @field_validator("ttl_days", "ttl_seconds", mode="before")
    @classmethod
    def _reject_explicit_null(cls, value: object) -> object:
        # 省略は「指定なし」だが、`null` は整数でない(`type`)。型は厳密(B 2.12)。
        if value is None:
            raise PydanticCustomError("int_type", "Input should be a valid integer")
        return value


class RegisterSourceBody(UpdateSourceBody):
    """EP-03 の本文。"""

    source_id: str
    # 値は検証しない(Crawler が `unsupported` にする)。
    connector_type: str

    @field_validator("source_id")
    @classmethod
    def _check_source_id_format(cls, value: str) -> str:
        if SOURCE_ID_PATTERN.fullmatch(value) is None:
            raise PydanticCustomError("string_pattern_mismatch", "Invalid source_id format")
        return value


class StartCrawlBody(RequestModel):
    """EP-06 の本文。本文なし・`{}` は、どちらも既定の `false`(B 4.1)。"""

    force_delete: bool = False
    rewrite_mode: bool = False


class ReleaseLockResponse(ResponseModel):
    """EP-08 の 200(B 4.3)。"""

    source_id: str
    # ロック文書を削除したら `true`。ロック文書がなければ `false`(何もしていない。冪等)。
    released: bool
    # `failed`(`lock_released`)にした実行中ジョブの ID。なければ `null`。
    failed_job_id: str | None
