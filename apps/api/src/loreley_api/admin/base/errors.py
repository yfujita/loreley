"""`AdminApiError` と、code ごとの生成関数(D 4.7)。

`message` は code ごとの固定の英語文(診断用)で、入力値・ID・例外のメッセージを含めない(A 5.2)。
Crawler 連携の code のうち、形が固定のもの(`crawler_*`・`config_invalid`)だけ生成関数を持つ。
`lock_held` など、Crawler の応答から `details` を作るものは `crawler_mapping` が組み立てる。
"""

from collections.abc import Sequence
from dataclasses import dataclass

from loreley_api.admin.base.codes import ErrorCode, Reason
from loreley_api.common.http.errors import INVALID_REQUEST_MESSAGE, ApiError

_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.INVALID_REQUEST: INVALID_REQUEST_MESSAGE,
    ErrorCode.UNAVAILABLE: "the data store is unavailable",
    ErrorCode.SOURCE_CONFIG_NOT_FOUND: "the data source is not found",
    ErrorCode.JOB_NOT_FOUND: "the job is not found",
    # 次の 2 つの文は B 2.5・2.7 の例による。残りは、同じ書き方(条件を述べる固定の英語文)で補った。
    ErrorCode.CONFIG_INVALID: "connector_config is invalid",
    ErrorCode.LOCK_HELD: "the source is locked by another job",
    ErrorCode.LOCK_IN_USE: "the lock is in use and cannot be released",
    ErrorCode.SOURCE_DELETING: "the source is being deleted",
    ErrorCode.MAINTENANCE_ENABLED: "maintenance is enabled",
    ErrorCode.SOURCE_ALREADY_EXISTS: "the source already exists",
    ErrorCode.JOB_NOT_CANCELLABLE: "the job cannot be cancelled",
    ErrorCode.JOB_ALREADY_FINISHED: "the job has already finished",
    ErrorCode.CRAWLER_ERROR: "the crawler returned an unexpected response",
    ErrorCode.CRAWLER_UNAVAILABLE: "the crawler is unavailable",
    ErrorCode.CRAWLER_UNREACHABLE: "the crawler is unreachable",
    ErrorCode.CRAWLER_RESPONSE_LOST: "the response from the crawler was lost",
}


class AdminApiError(ApiError):
    """Admin API が統一エラー形式の応答にしたい失敗。`common.http` のハンドラが応答に変換する。"""

    def __init__(
        self,
        code: ErrorCode,
        status_code: int,
        *,
        retryable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(
            status_code, code.value, _MESSAGES[code], retryable=retryable, details=details
        )


@dataclass(frozen=True)
class FieldViolation:
    """入力の違反 1 件。`field` は Admin API のリクエストの項目名で、値は載せない(A 5.2)。"""

    field: str
    reason: Reason
    # `config_invalid` のときだけ、違反の種類の固定文(B 2.4)。
    detail: str | None = None


def invalid_request(violations: Sequence[FieldViolation] = ()) -> AdminApiError:
    """400 `invalid_request`。項目の違反がなければ(JSON として読めないなど)`details` を付けない。"""
    if not violations:
        return AdminApiError(ErrorCode.INVALID_REQUEST, 400)
    errors = [_error_entry(violation) for violation in violations]
    return AdminApiError(ErrorCode.INVALID_REQUEST, 400, details={"errors": errors})


def _error_entry(violation: FieldViolation) -> dict[str, str]:
    entry = {"field": violation.field, "reason": violation.reason.value}
    if violation.detail is not None:
        entry["detail"] = violation.detail
    return entry


def unavailable() -> AdminApiError:
    """503 `unavailable`: その EP の主たる読み取りが、再試行しても失敗した。"""
    return AdminApiError(ErrorCode.UNAVAILABLE, 503, retryable=True)


def source_config_not_found() -> AdminApiError:
    return AdminApiError(ErrorCode.SOURCE_CONFIG_NOT_FOUND, 404)


def job_not_found() -> AdminApiError:
    return AdminApiError(ErrorCode.JOB_NOT_FOUND, 404)


def config_invalid(violations: Sequence[FieldViolation], crawler_message: str) -> AdminApiError:
    """400 `config_invalid`(B 2.5)。`violations` が空なら、項目を分解できなかった(`errors` は空)。

    `crawler_message` は、Crawler が入力値・errno・パスを含めない固定文として返したもの(B 2.5)。
    """
    errors = [_error_entry(violation) for violation in violations]
    return AdminApiError(
        ErrorCode.CONFIG_INVALID,
        400,
        details={"errors": errors, "crawler_message": crawler_message},
    )


def crawler_error() -> AdminApiError:
    """502: Crawler の想定外・契約外の応答(B 2.6)。"""
    return AdminApiError(ErrorCode.CRAWLER_ERROR, 502)


def crawler_unreachable() -> AdminApiError:
    """503: Crawler に届かなかった(送る前の失敗。再試行してよい)。"""
    return AdminApiError(ErrorCode.CRAWLER_UNREACHABLE, 503, retryable=True)


def crawler_response_lost() -> AdminApiError:
    """504: 送った後に応答が来なかった。操作の結果は不明(B 2.3)。"""
    return AdminApiError(ErrorCode.CRAWLER_RESPONSE_LOST, 504, details={"outcome_unknown": True})
