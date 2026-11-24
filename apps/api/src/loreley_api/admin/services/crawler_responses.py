"""Crawler の成功の本文(JSON のオブジェクト)を、Admin API の DTO にする(EP-03〜08)。

Crawler クライアントは「JSON のオブジェクトで、成功のステータスが API の期待どおり」までしか
確かめない(C 4.2)ので、項目の型はここで確かめる。読めない・足りない項目があれば `None`(呼び出し側が
502 `crawler_error` にする。操作は実行済みかもしれない。B 10.2)。DTO は `null` を許さない項目を
持つので、読めない値を `null` にして通すことはしない(EP-02 の保存値の読み取りとは違う。B 2.2)。
"""

from collections.abc import Mapping
from typing import Any

from loreley_api.admin.base.codes import JobStatus, JobTrigger, JobType
from loreley_api.admin.derivation.settings_view import read_source_settings
from loreley_api.admin.derivation.values import (
    read_bool,
    read_choice,
    read_instant_text,
    read_non_empty_str,
)
from loreley_api.admin.schemas.common import JobAccepted, SourceSettings
from loreley_api.admin.schemas.jobs import CancelJobResponse
from loreley_api.admin.schemas.sources import ReleaseLockResponse


def to_source_settings(body: Mapping[str, Any]) -> SourceSettings | None:
    """登録・更新の 200・201 の本文(保存内容)。TTL・しきい値は、応答の単位に換算する(B 2.8)。"""
    source_id = read_non_empty_str(body.get("source_id"))
    if source_id is None:
        return None
    view = read_source_settings(source_id, body)
    if view.malformed:
        return None
    return SourceSettings.model_validate(
        {
            "source_id": view.source_id,
            "connector_type": view.connector_type,
            "connector_config": dict(view.connector_config or {}),
            "ttl_seconds": view.ttl_seconds,
            "ttl_days": view.ttl_days,
            "ratio_threshold_percent": view.ratio_threshold_percent,
            "min_delete_count": view.min_delete_count,
            "schedule_cron": view.schedule_cron,
            "status": view.status,
            "updated_at": view.updated_at,
        }
    )


def to_job_accepted(body: Mapping[str, Any], *, has_options: bool) -> JobAccepted | None:
    """EP-05・06 の 202 の本文。`has_options` は、`force_delete`・`rewrite_mode` を含むか(EP-06)。

    EP-05(`source_delete`)の応答は 2 項目を含まないので、`null` にする(B 3.5)。
    """
    job_id = read_non_empty_str(body.get("job_id"))
    job_type = read_choice(body.get("job_type"), JobType)
    source_id = read_non_empty_str(body.get("source_id"))
    status = read_choice(body.get("status"), JobStatus)
    trigger = read_choice(body.get("trigger"), JobTrigger)
    queued_at = read_instant_text(body.get("queued_at"))
    force_delete = read_bool(body.get("force_delete")) if has_options else None
    rewrite_mode = read_bool(body.get("rewrite_mode")) if has_options else None
    required = [job_id, job_type, source_id, status, trigger, queued_at]
    if has_options:
        required += [force_delete, rewrite_mode]
    if any(value is None for value in required):
        return None
    return JobAccepted.model_validate(
        {
            "job_id": job_id,
            "job_type": job_type,
            "source_id": source_id,
            "status": status,
            "trigger": trigger,
            "force_delete": force_delete,
            "rewrite_mode": rewrite_mode,
            "queued_at": queued_at,
        }
    )


def to_cancel_job(body: Mapping[str, Any]) -> CancelJobResponse | None:
    job_id = read_non_empty_str(body.get("job_id"))
    status = read_choice(body.get("status"), JobStatus)
    if job_id is None or status is None:
        return None
    return CancelJobResponse(job_id=job_id, status=status)


def to_release_lock(body: Mapping[str, Any]) -> ReleaseLockResponse | None:
    source_id = read_non_empty_str(body.get("source_id"))
    released = read_bool(body.get("released"))
    failed_job_id = read_non_empty_str(body.get("failed_job_id"))
    # `failed_job_id` は、キーがあり、値が文字列または `null`(`failed` にしたジョブがないとき)。
    has_valid_failed_job_id = "failed_job_id" in body and (
        failed_job_id is not None or body["failed_job_id"] is None
    )
    if source_id is None or released is None or not has_valid_failed_job_id:
        return None
    return ReleaseLockResponse(source_id=source_id, released=released, failed_job_id=failed_job_id)
