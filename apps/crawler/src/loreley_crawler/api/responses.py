"""`jobs`・`sources` の結果型から HTTP 応答への写像(crawler-api 4章)。

結果の判断(受付の拒否・ロック・設定の状態)は `jobs`・`sources` が済ませている。ここは結果の
種類をステータス・エラーコード・本文に写すだけで、判断をしない(R4)。結果型の全バリアントを
`match` で列挙し、写像にない型は `TypeError`(500)にする(取りこぼしを黙って成功にしない)。
"""

from typing import Any, NoReturn

from fastapi.responses import JSONResponse

from loreley_crawler.api.errors import error_response
from loreley_crawler.common.timestamps import format_instant
from loreley_crawler.jobs import (
    Accepted,
    AcceptedJob,
    AdmissionResult,
    Cancelled,
    CancelRequested,
    CancelResult,
    ExistingJob,
    JobAlreadyFinished,
    JobNotCancellable,
    JobNotFound,
    JobStatus,
    JobType,
    LockAlreadyHeld,
    LockInUse,
    LockReleased,
    MaintenanceEnabled,
    NoLockToRelease,
    ReleaseLockResult,
    SourceConfigNotFound,
    SourceDeleting,
)
from loreley_crawler.sources import (
    AlreadyRegistered,
    Registered,
    RegisterResult,
    RegistrationConflict,
    SourceIsDeleting,
    SourceNotFound,
    SourceRecord,
    Unchanged,
    Updated,
    UpdateResult,
)


def admission_response(result: AdmissionResult) -> JSONResponse:
    """クロール起動・ソース削除ジョブ起動(4.1・4.6)。"""
    match result:
        case Accepted(job=job):
            return JSONResponse(status_code=202, content=_accepted_job_body(job))
        case SourceConfigNotFound():
            return error_response(
                404, "source_config_not_found", "the source configuration does not exist"
            )
        case SourceDeleting():
            return error_response(409, "source_deleting", "the source is being deleted")
        case MaintenanceEnabled():
            return error_response(409, "maintenance_enabled", "maintenance is enabled")
        case LockAlreadyHeld(existing_job=existing_job):
            return error_response(
                409,
                "lock_held",
                "the source is locked by another job",
                details={"existing_job": _existing_job_body(existing_job)},
            )
    _unmapped(result)


def cancel_response(result: CancelResult) -> JSONResponse:
    """取り消し(4.2)。"""
    match result:
        case Cancelled(job_id=job_id):
            return JSONResponse(
                status_code=200, content={"job_id": job_id, "status": JobStatus.CANCELLED.value}
            )
        case CancelRequested(job_id=job_id):
            return JSONResponse(
                status_code=202, content={"job_id": job_id, "status": JobStatus.RUNNING.value}
            )
        case JobNotFound():
            return error_response(404, "job_not_found", "the job does not exist")
        case JobNotCancellable():
            return error_response(409, "job_not_cancellable", "the job cannot be cancelled")
        case JobAlreadyFinished(status=status):
            return error_response(
                409,
                "job_already_finished",
                "the job has already finished",
                details={"status": status.value},
            )
    _unmapped(result)


def release_lock_response(source_id: str, result: ReleaseLockResult) -> JSONResponse:
    """ロック解放(4.3)。"""
    match result:
        case LockReleased(failed_job_id=failed_job_id):
            return JSONResponse(
                status_code=200,
                content={"source_id": source_id, "released": True, "failed_job_id": failed_job_id},
            )
        case NoLockToRelease():
            return JSONResponse(
                status_code=200,
                content={"source_id": source_id, "released": False, "failed_job_id": None},
            )
        case LockInUse(existing_job=existing_job):
            return error_response(
                409,
                "lock_in_use",
                "the lock is in use",
                details={"existing_job": _existing_job_body(existing_job)},
            )
    _unmapped(result)


def registration_response(result: RegisterResult) -> JSONResponse:
    """設定の登録(4.4.2)。"""
    match result:
        case Registered(record=record):
            return JSONResponse(status_code=201, content=_source_body(record))
        case AlreadyRegistered(record=record):
            return JSONResponse(status_code=200, content=_source_body(record))
        case RegistrationConflict(existing_status=existing_status):
            # 既存の設定が形式不正で `status` が読めないときは null。
            status = existing_status.value if existing_status is not None else None
            return error_response(
                409,
                "source_already_exists",
                "the source already exists",
                details={"status": status},
            )
    _unmapped(result)


def update_response(result: UpdateResult) -> JSONResponse:
    """設定の更新(4.4.3)。"""
    match result:
        case Updated(record=record) | Unchanged(record=record):
            return JSONResponse(status_code=200, content=_source_body(record))
        case SourceNotFound():
            return error_response(
                404, "source_config_not_found", "the source configuration does not exist"
            )
        case SourceIsDeleting():
            return error_response(409, "source_deleting", "the source is being deleted")
    _unmapped(result)


def _accepted_job_body(job: AcceptedJob) -> dict[str, Any]:
    body: dict[str, Any] = {
        "job_id": job.job_id,
        "job_type": job.job_type.value,
        "source_id": job.source_id,
        "status": job.status.value,
        "trigger": job.trigger.value,
    }
    if job.job_type is JobType.CRAWL:  # ソース削除ジョブは含めない(4.6)
        body["force_delete"] = job.force_delete
        body["rewrite_mode"] = job.rewrite_mode
    body["queued_at"] = format_instant(job.queued_at)
    return body


def _existing_job_body(job: ExistingJob) -> dict[str, Any]:
    """ジョブ記録がない・形式不正の項目は null(孤児ロック・形式不正なジョブ記録)。"""
    return {
        "job_id": job.job_id,
        "job_type": job.job_type.value if job.job_type is not None else None,
        "status": job.status.value if job.status is not None else None,
        "trigger": job.trigger.value if job.trigger is not None else None,
        "lease_expires_at": (
            format_instant(job.lease_expires_at) if job.lease_expires_at is not None else None
        ),
    }


def _source_body(record: SourceRecord) -> dict[str, Any]:
    return {
        "source_id": record.source_id,
        "connector_type": record.connector_type,
        "connector_config": record.connector_config,
        "ttl": record.ttl,
        "ratio_threshold": record.ratio_threshold,
        "min_delete_count": record.min_delete_count,
        "schedule_cron": record.schedule_cron,
        "status": record.status.value,
        "updated_at": format_instant(record.updated_at),
    }


def _unmapped(result: object) -> NoReturn:
    raise TypeError(f"no HTTP mapping for {type(result).__name__}")
