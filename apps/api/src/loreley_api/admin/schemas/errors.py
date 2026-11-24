"""エラー応答の OpenAPI 上の宣言(A 5.2・5.4。D 3章)。

実際のエラー応答は `common/http` のハンドラが組み立てる JSON で、ここのモデルは OpenAPI の
記述のためだけにある(応答の検証や生成には使わない)。形は A 5.2 の共通形式で、`details` の
うち B 2.3・2.7 が定めるキーを型にし、それ以外のキーも許す(`additionalProperties: true`)。

`code` は列挙にしない。共通 code(`not_found` など)や将来の code が増えても、型の生成物が
壊れないようにするため。操作ごとに返しうる code は、応答の `description` に書く。
"""

from collections import defaultdict
from http import HTTPStatus
from typing import Any

from pydantic import BaseModel, ConfigDict

from loreley_api.admin.base.codes import ErrorCode, LockState, Reason
from loreley_api.admin.schemas.common import ExistingJob


class FieldError(BaseModel):
    """`details.errors[]` の 1 件。値は載せない(A 5.2)。"""

    field: str
    reason: Reason
    # `config_invalid` のときだけ、違反の種類の固定文(B 2.4)。
    detail: str | None = None


class RequestedOptions(BaseModel):
    """409 `lock_held`(EP-06)の `details.requested`: 受け取った指定(B 2.7)。"""

    force_delete: bool
    rewrite_mode: bool


class ErrorDetails(BaseModel):
    """`details`。code によって持つキーが違う(どれも任意)。"""

    model_config = ConfigDict(extra="allow")

    # 400 `invalid_request`・`config_invalid`。
    errors: list[FieldError] | None = None
    # 400 `config_invalid`。Crawler の固定文(B 2.5)。
    crawler_message: str | None = None
    # 409 `lock_held`・`lock_in_use`(B 2.7)。
    existing_job: ExistingJob | None = None
    lock_state: LockState | None = None
    # 409 `lock_held`(EP-06 だけ)。常に `false`。
    options_applied: bool | None = None
    requested: RequestedOptions | None = None
    # 409 `source_already_exists`・`job_already_finished`。
    status: str | None = None
    # 504 `crawler_response_lost`。常に `true`。
    outcome_unknown: bool | None = None


class ErrorBody(BaseModel):
    code: str
    # 固定の英語文(診断用)。入力値・パス・例外のメッセージを含まない。
    message: str
    retryable: bool
    details: ErrorDetails | None = None


class ErrorResponse(BaseModel):
    """エラー応答の共通スキーマ(A 5.2)。"""

    error: ErrorBody


# code → HTTP ステータス(B 2.3。code とステータスは 1 対 1)。
STATUS_OF_CODE: dict[ErrorCode, int] = {
    ErrorCode.INVALID_REQUEST: 400,
    ErrorCode.CONFIG_INVALID: 400,
    ErrorCode.SOURCE_CONFIG_NOT_FOUND: 404,
    ErrorCode.JOB_NOT_FOUND: 404,
    ErrorCode.LOCK_HELD: 409,
    ErrorCode.LOCK_IN_USE: 409,
    ErrorCode.SOURCE_DELETING: 409,
    ErrorCode.MAINTENANCE_ENABLED: 409,
    ErrorCode.SOURCE_ALREADY_EXISTS: 409,
    ErrorCode.JOB_NOT_CANCELLABLE: 409,
    ErrorCode.JOB_ALREADY_FINISHED: 409,
    ErrorCode.CRAWLER_ERROR: 502,
    ErrorCode.UNAVAILABLE: 503,
    ErrorCode.CRAWLER_UNAVAILABLE: 503,
    ErrorCode.CRAWLER_UNREACHABLE: 503,
    ErrorCode.CRAWLER_RESPONSE_LOST: 504,
}

# Crawler へ中継する EP(EP-03〜08)が、Crawler の失敗として共通に返しうる code(B 2.3)。
CRAWLER_RELAY_ERROR_CODES: tuple[ErrorCode, ...] = (
    ErrorCode.CRAWLER_ERROR,
    ErrorCode.CRAWLER_UNAVAILABLE,
    ErrorCode.CRAWLER_UNREACHABLE,
    ErrorCode.CRAWLER_RESPONSE_LOST,
)


def error_responses(*codes: ErrorCode) -> dict[int | str, dict[str, Any]]:
    """`responses=` に渡す、エラー応答の宣言。ステータスごとに、返しうる code を説明に書く。

    400 `invalid_request` は、どの EP も返しうる(未知のクエリ・形式違反。A 5.1・5.3)ので、
    `codes` になくても必ず宣言する。FastAPI が既定で足す 422 は、基盤が 400 に変えるので
    宣言しない(`app.py` が取り除く)。
    """
    codes_by_status: dict[int, list[ErrorCode]] = defaultdict(list)
    for code in (ErrorCode.INVALID_REQUEST, *codes):
        status = STATUS_OF_CODE[code]
        if code not in codes_by_status[status]:
            codes_by_status[status].append(code)
    return {
        status: {
            "model": ErrorResponse,
            "description": f"{HTTPStatus(status).phrase}. error.code: "
            + ", ".join(code.value for code in codes_in_status),
        }
        for status, codes_in_status in sorted(codes_by_status.items())
    }
