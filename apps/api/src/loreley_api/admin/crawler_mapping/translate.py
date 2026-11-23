"""Crawler クライアントの返り値を Admin API の成功・エラーに写す(B 2.6・9.2。C 4.4。D 4.7)。

写像の中身は `table.py` のデータで、ここは表の適用だけを行う。純粋な関数(I/O・時計・環境変数なし)。
表にない組み合わせ、契約外の応答、想定外の形は、すべて 502 `crawler_error`(安全側)。

`lock_state` は Admin API が OpenSearch を読んで導出する値で(B 2.7)、この関数は読まない。
409 `lock_held`・`lock_in_use` のとき、呼び出し側(`services`)が `needs_lock_state` で要否を確かめ、
先に読んで渡す。読めなければ `LockState.UNKNOWN`(ステータス・`existing_job` は変えない。C 4.6)。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from loreley_api.admin.base.codes import LockState, Reason
from loreley_api.admin.base.errors import (
    AdminApiError,
    FieldViolation,
    config_invalid,
    crawler_error,
    crawler_response_lost,
    crawler_unreachable,
    invalid_request,
)
from loreley_api.admin.crawler_mapping.table import (
    SENT_TTL_FIELD,
    TABLE,
    BranchOnField,
    CrawlerOperation,
    DecomposeConfigInvalid,
    DetailKind,
    Outcome,
    Passthrough,
    RenameFields,
)
from loreley_api.infrastructure.crawler_client import (
    CrawlerContractViolation,
    CrawlerRejected,
    CrawlerResult,
    CrawlerSucceeded,
    CrawlerTransportFailed,
)

TtlField = Literal["ttl_days", "ttl_seconds"]

_LOCK_DETAIL_KINDS = frozenset(
    {DetailKind.LOCK_HELD, DetailKind.LOCK_HELD_WITH_OPTIONS, DetailKind.LOCK_IN_USE}
)
_EXISTING_JOB_OPTIONAL_TEXT_FIELDS = ("job_type", "status", "trigger", "lease_expires_at")


@dataclass(frozen=True)
class RequestedOptions:
    """EP-06 が受け取った指定。409 `lock_held` の `details.requested` に載せる(B 2.7)。"""

    force_delete: bool
    rewrite_mode: bool


def needs_lock_state(operation: CrawlerOperation, result: CrawlerResult) -> bool:
    """この結果の写像が `lock_state` を使うか(`services` が、読み取りの要否を決めるために使う)。"""
    if not isinstance(result, CrawlerRejected):
        return False
    outcome = TABLE.get((operation, result.status, result.code))
    return isinstance(outcome, Passthrough) and outcome.details in _LOCK_DETAIL_KINDS


def translate(
    operation: CrawlerOperation,
    result: CrawlerResult,
    *,
    lock_state: LockState = LockState.UNKNOWN,
    requested: RequestedOptions | None = None,
    ttl_field: TtlField = "ttl_seconds",
) -> CrawlerSucceeded | AdminApiError:
    """成功はそのまま返す(DTO への変換は `services`)。失敗は `AdminApiError`(呼び出し側が送出する)。

    - `lock_state`: 409 `lock_held`・`lock_in_use` の `details.lock_state`。
    - `requested`: EP-06 の 409 `lock_held` の `details.requested`(EP-06 のとき必須)。
    - `ttl_field`: EP-03・04 で、リクエストが TTL を指定した項目(Crawler の `ttl` の違反の写し先)。
    """
    match result:
        case CrawlerSucceeded():
            return result
        case CrawlerTransportFailed(phase="before_send"):
            return crawler_unreachable()
        case CrawlerTransportFailed():
            return crawler_response_lost()
        case CrawlerContractViolation():
            return crawler_error()
        case CrawlerRejected():
            outcome = TABLE.get((operation, result.status, result.code))
            if outcome is None:
                return crawler_error()
            return _apply(outcome, result, lock_state, requested, ttl_field)


def _apply(
    outcome: Outcome,
    rejected: CrawlerRejected,
    lock_state: LockState,
    requested: RequestedOptions | None,
    ttl_field: TtlField,
) -> AdminApiError:
    match outcome:
        case Passthrough():
            return _passthrough(outcome, rejected, lock_state, requested)
        case RenameFields(fields=fields):
            return _rename_invalid_fields(fields, rejected, ttl_field)
        case BranchOnField(field=field, when_present=when_present, otherwise=otherwise):
            chosen = when_present if field in _error_fields(rejected) else otherwise
            return _passthrough(chosen, rejected, lock_state, requested)
        case DecomposeConfigInvalid():
            return _config_invalid(rejected)


def _passthrough(
    outcome: Passthrough,
    rejected: CrawlerRejected,
    lock_state: LockState,
    requested: RequestedOptions | None,
) -> AdminApiError:
    details = _details_of(outcome.details, rejected, lock_state, requested)
    if details is None:
        return crawler_error()  # 必要な付随情報が Crawler の応答になかった(契約外)
    return AdminApiError(
        outcome.code,
        outcome.status,
        retryable=outcome.retryable,
        details=details or None,
    )


def _details_of(
    kind: DetailKind,
    rejected: CrawlerRejected,
    lock_state: LockState,
    requested: RequestedOptions | None,
) -> dict[str, object] | None:
    """`details` の中身。空の dict は「`details` なし」。`None` は、載せるべき情報が読めない。"""
    if kind is DetailKind.NONE:
        return {}
    details = rejected.details or {}
    if kind is DetailKind.STATUS:
        # 既存の設定が形式不正で読めないとき(`source_already_exists`)は `null`。
        status = details.get("status")
        return {"status": status if isinstance(status, str) else None}
    existing_job = _existing_job(details.get("existing_job"))
    if existing_job is None:
        return None
    lock_details: dict[str, object] = {
        "existing_job": existing_job,
        "lock_state": lock_state.value,
    }
    if kind is not DetailKind.LOCK_HELD_WITH_OPTIONS:
        return lock_details
    if requested is None:
        raise ValueError("requested is required for a lock_held conflict of start_crawl")
    # 指定は、起動していないので既存のジョブにも反映されない(B 2.7)。
    return {
        "options_applied": False,
        "requested": {
            "force_delete": requested.force_delete,
            "rewrite_mode": requested.rewrite_mode,
        },
        **lock_details,
    }


def _existing_job(value: object) -> dict[str, str | None] | None:
    """Crawler の `details.existing_job` から 5 項目だけを、型を確かめて取り込む(C 4.4)。

    `job_id` が文字列でなければ読めない(`None`)。ほかの 4 項目は、文字列でなければ `null`
    (ジョブ記録がない・値が読めない。B 2.11)。`lease_expires_at` の番兵値
    (`0001-01-01T00:00:00.000Z`)は変換せず、そのまま通す(I-73)。
    """
    if not isinstance(value, dict) or not isinstance(value.get("job_id"), str):
        return None
    existing_job: dict[str, str | None] = {"job_id": value["job_id"]}
    for name in _EXISTING_JOB_OPTIONAL_TEXT_FIELDS:
        text = value.get(name)
        existing_job[name] = text if isinstance(text, str) else None
    return existing_job


def _error_entries(rejected: CrawlerRejected) -> list[Mapping[str, Any]]:
    errors = (rejected.details or {}).get("errors")
    if not isinstance(errors, list):
        return []
    return [entry for entry in errors if isinstance(entry, dict)]


def _error_fields(rejected: CrawlerRejected) -> set[object]:
    return {entry.get("field") for entry in _error_entries(rejected)}


def _rename_invalid_fields(
    fields: Mapping[str, str], rejected: CrawlerRejected, ttl_field: TtlField
) -> AdminApiError:
    violations: list[FieldViolation] = []
    for entry in _error_entries(rejected):
        crawler_field = entry.get("field")
        admin_field = fields.get(crawler_field) if isinstance(crawler_field, str) else None
        reason = _reason_of(entry.get("reason"))
        if admin_field is None or reason is None:
            continue
        violations.append(
            FieldViolation(ttl_field if admin_field == SENT_TTL_FIELD else admin_field, reason)
        )
    if not violations:
        return crawler_error()  # Admin API が送らない・検証済みの項目の違反(B 2.6)
    return invalid_request(violations)


def _reason_of(value: object) -> Reason | None:
    """Crawler の `reason` を、そのまま Admin API の値にする。知らない値(`read_only`)は `None`。"""
    try:
        return Reason(value)
    except ValueError:
        return None


def _config_invalid(rejected: CrawlerRejected) -> AdminApiError:
    parsed = rejected.config_invalid
    if parsed is None:
        return crawler_error()
    violation = parsed.violation
    violations = (
        [FieldViolation(violation.field, Reason.CONFIG_INVALID, detail=violation.detail)]
        if violation is not None
        else []
    )
    return config_invalid(violations, parsed.crawler_message)
