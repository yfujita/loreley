"""`deletion.*`(EP-10。C 5.4・5.7。B 5.2)。

`summary` はジョブ記録の `deletion_summary`、`current` は `loreley-deletions` の削除結果、
`settings` はジョブ記録の `settings_snapshot` が元。項目ごとに、読めない値は `None`(C 5.0)。
`current`・`current_state`・`fetched_at` を決める読み取りの要否(実行待ちは読まない)は
`services.job_queries` が決める。
"""

from dataclasses import dataclass

from loreley_api.admin.base.codes import DeletionConfirmation
from loreley_api.admin.derivation.units import ratio_to_percent
from loreley_api.admin.derivation.values import (
    Document,
    read_bool,
    read_choice,
    read_instant_text,
    read_int,
    read_mapping,
    read_number,
    read_str,
)


@dataclass(frozen=True)
class DeletionSummaryView:
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
    # 確認を打ち切ったときだけ値がある。
    observed_at: str | None


def read_deletion_summary(job_source: Document) -> DeletionSummaryView | None:
    """ジョブ記録の `deletion_summary`。なければ(オブジェクトでなければ)`None`。"""
    summary = read_mapping(job_source.get("deletion_summary"))
    if summary is None:
        return None
    return DeletionSummaryView(
        status=read_str(summary.get("status")),
        reason=read_str(summary.get("reason")),
        forced=read_bool(summary.get("forced")),
        target_count=read_int(summary.get("target_count")),
        denominator=read_int(summary.get("denominator")),
        deleted_count=read_int(summary.get("deleted_count")),
        enumerated_count=read_int(summary.get("enumerated_count")),
        n_seen=read_int(summary.get("n_seen")),
        e_missing=read_int(summary.get("e_missing")),
        finish_received_at=read_instant_text(summary.get("finish_received_at")),
        deletion_started_at=read_instant_text(summary.get("deletion_started_at")),
        finished_at=read_instant_text(summary.get("finished_at")),
        observed_at=read_instant_text(summary.get("observed_at")),
    )


def read_deletion_confirmation(job_source: Document) -> DeletionConfirmation | None:
    """確認に入っていないジョブ(値がない・許される値にない)は `None`。"""
    return read_choice(job_source.get("confirmation"), DeletionConfirmation)


@dataclass(frozen=True)
class DeletionCurrentView:
    status: str | None
    reason: str | None
    reason_detail: str | None
    forced: bool | None
    target_count: int | None
    denominator: int | None
    deleted_count: int | None
    ended_at: str | None


def read_deletion_current(result_source: Document) -> DeletionCurrentView:
    """`loreley-deletions` の削除結果(`record_type=deletion_result`)の現在値。"""
    return DeletionCurrentView(
        status=read_str(result_source.get("status")),
        reason=read_str(result_source.get("reason")),
        reason_detail=read_str(result_source.get("reason_detail")),
        forced=read_bool(result_source.get("forced")),
        target_count=read_int(result_source.get("target_count")),
        denominator=read_int(result_source.get("denominator")),
        deleted_count=read_int(result_source.get("deleted_count")),
        ended_at=read_instant_text(result_source.get("ended_at")),
    )


@dataclass(frozen=True)
class DeletionSettingsView:
    ttl_seconds: int | None
    ratio_threshold_percent: int | float | None
    min_delete_count: int | None


def read_deletion_settings(job_source: Document) -> DeletionSettingsView | None:
    """ジョブ記録の `settings_snapshot`(`ttl`・`ratio_threshold`・`min_delete_count`)を、
    応答の単位(秒・%)にする。スナップショットがない(開始前に失敗した)ときは `None`。
    """
    snapshot = read_mapping(job_source.get("settings_snapshot"))
    if snapshot is None:
        return None
    ratio = read_number(snapshot.get("ratio_threshold"))
    return DeletionSettingsView(
        ttl_seconds=read_int(snapshot.get("ttl")),
        ratio_threshold_percent=ratio_to_percent(ratio) if ratio is not None else None,
        min_delete_count=read_int(snapshot.get("min_delete_count")),
    )
