"""`lock_state` の 7 値の導出と、`lock.job`・`lock.acquired_at`(C 5.1。B 2.9)。

**ロック文書から始め、ジョブ記録は `lock.job_id` で引く**(読む順序はロック文書 → ジョブ記録。
逆にすると、ロックの解放・ジョブの終了の途中を誤って `stalled` と判定する)。この関数は、読み終えた
結果を受けて判定するだけで、読む順序は `services.lock_view` が守る。

ロック文書の読み取り自体が失敗したとき(表の順 1)は、ここでは扱わない(EP-02 は `lock=null`、
409 の付随情報は `unknown`。呼び出し側が決める)。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from loreley_api.admin.base.codes import (
    TERMINAL_JOB_STATUSES,
    JobStatus,
    JobTrigger,
    JobType,
    LockState,
)
from loreley_api.admin.derivation.values import (
    Document,
    read_choice,
    read_instant,
    read_instant_text,
    read_mapping,
    read_non_empty_str,
)


@dataclass(frozen=True)
class JobFound:
    source: Document


@dataclass(frozen=True)
class JobAbsent:
    """ジョブ記録がない(`found=false`、または `record_type` が `job` でない)。"""


@dataclass(frozen=True)
class JobReadFailed:
    """ジョブ記録の読み取りが失敗した。「記録なし」とは読まない。"""


type JobLookup = JobFound | JobAbsent | JobReadFailed


@dataclass(frozen=True)
class ExistingJobView:
    """`lock.job`・`details.existing_job`(B 2.11 の `ExistingJob`)。"""

    job_id: str
    # ジョブ記録がない・読めない値のときは `None`。
    job_type: JobType | None
    status: JobStatus | None
    trigger: JobTrigger | None
    # ロック文書のリース期限。実行待ちや読めない値は `None`。
    lease_expires_at: str | None


@dataclass(frozen=True)
class LockDerivation:
    state: LockState
    job: ExistingJobView | None
    acquired_at: str | None


def derive_lock(
    lock_source: object | None,
    job: JobLookup,
    *,
    now: datetime,
    grace_seconds: float,
) -> LockDerivation:
    """`lock_source` はロック文書の `_source`(文書がなければ `None`)。

    `job` は、`lock_source.job_id` で引いたジョブ記録の結果。`job_id` が文字列で空でないとき
    だけ引くので、そうでなければ何を渡しても使わない。
    """
    if lock_source is None:
        return LockDerivation(LockState.NONE, job=None, acquired_at=None)
    lock = read_mapping(lock_source)
    if lock is None:
        return LockDerivation(LockState.UNKNOWN, job=None, acquired_at=None)

    acquired_at_text = read_instant_text(lock.get("acquired_at"))
    job_id = read_non_empty_str(lock.get("job_id"))
    if job_id is None:
        state = _state_without_job_record(lock, now, grace_seconds)
        return LockDerivation(state, job=None, acquired_at=acquired_at_text)

    view = _existing_job_view(job_id, lock, job)
    state = _state_with_job_lookup(lock, job, view, now, grace_seconds)
    return LockDerivation(state, job=view, acquired_at=acquired_at_text)


def _existing_job_view(job_id: str, lock: Document, job: JobLookup) -> ExistingJobView:
    lease_expires_at = read_instant_text(lock.get("lease_expires_at"))
    if not isinstance(job, JobFound):
        return ExistingJobView(job_id, None, None, None, lease_expires_at)
    return ExistingJobView(
        job_id=job_id,
        job_type=read_choice(job.source.get("job_type"), JobType),
        status=read_choice(job.source.get("status"), JobStatus),
        trigger=read_choice(job.source.get("trigger"), JobTrigger),
        lease_expires_at=lease_expires_at,
    )


def _state_with_job_lookup(
    lock: Document, job: JobLookup, view: ExistingJobView, now: datetime, grace_seconds: float
) -> LockState:
    match job:
        case JobReadFailed():
            return LockState.UNKNOWN
        case JobAbsent():
            return _state_without_job_record(lock, now, grace_seconds)
        case JobFound():
            return _state_of_job(lock, view, now)


def _state_without_job_record(lock: Document, now: datetime, grace_seconds: float) -> LockState:
    """ジョブ記録がない。取得から猶予以内なら受付の途中(`just_acquired`)、それ以外は `orphan`。

    猶予の境界はちょうど `grace_seconds` で `orphan`。`acquired_at` が読めない値も `orphan`。
    `just_acquired` と `orphan` は排他(B 2.9)。
    """
    acquired_at = read_instant(lock.get("acquired_at"))
    if acquired_at is not None and now - acquired_at < timedelta(seconds=grace_seconds):
        return LockState.JUST_ACQUIRED
    return LockState.ORPHAN


def _state_of_job(lock: Document, view: ExistingJobView, now: datetime) -> LockState:
    status, job_type = view.status, view.job_type
    if status is None or job_type is None:
        return LockState.UNKNOWN
    if status in TERMINAL_JOB_STATUSES:
        return LockState.ORPHAN
    held = LockState.HELD_CRAWL if job_type is JobType.CRAWL else LockState.HELD_DELETE
    if status is JobStatus.QUEUED:
        return held
    # `running`。期限が読めて超えていなければ保持中。`null`・読めない値・期限切れは
    # `lease_expired`。
    lease_expires_at = read_instant(lock.get("lease_expires_at"))
    if lease_expires_at is not None and now < lease_expires_at:
        return held
    return LockState.LEASE_EXPIRED
