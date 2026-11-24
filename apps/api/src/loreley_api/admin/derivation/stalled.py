"""`stalled`・`cancellable`(C 5.2。B 2.9)。

`stalled` は、実行中(保存上 `running`)でリース期限を過ぎていること。期限が `null`・読めない値も
過ぎたとみなす。ロックの解放・ジョブの終了の途中を誤って `stalled` と判定しない(偽陽性を避ける)
ための読み取りの手順(ロックを読み、不一致なら確認読み)は `services.stalled_check` が行い、ここは
読み終えた結果の判定だけを持つ。
"""

from dataclasses import dataclass
from datetime import datetime

from loreley_api.admin.base.codes import JobStatus, JobType
from loreley_api.admin.derivation.values import read_instant, read_mapping
from loreley_api.common.timestamps import format_instant


@dataclass(frozen=True)
class StalledJudgement:
    stalled: bool
    # EP-10 の `lease_expires_at`。ロック文書が一致し、日時として読めるときだけ値がある。
    lease_expires_at: str | None


def judge_by_lock(
    lock_source: object | None, job_id: str, now: datetime
) -> StalledJudgement | None:
    """`running` のジョブ `job_id` を、そのソースのロック文書で判定する。

    ロック文書がない、または別のジョブのものなら `None`。確認読みが要る(読み直しで、ジョブが
    終わっていたのか、本当に止まっているのかが決まる。C 5.2 の手順 3)。
    """
    lock = read_mapping(lock_source)
    if lock is None or lock.get("job_id") != job_id:
        return None
    lease_expires_at = read_instant(lock.get("lease_expires_at"))
    if lease_expires_at is None:
        return StalledJudgement(stalled=True, lease_expires_at=None)
    return StalledJudgement(
        stalled=now >= lease_expires_at, lease_expires_at=format_instant(lease_expires_at)
    )


def is_cancellable(
    job_type: JobType | None, status: JobStatus | None, stalled: bool | None
) -> bool:
    """`crawl` で、実行待ち、または実行中でリース期限内。

    `stalled` が `null`(判定できない)のときは `false`(安全側)。`status` が読めなければ `false`。
    """
    if job_type is not JobType.CRAWL:
        return False
    if status is JobStatus.QUEUED:
        return True
    return status is JobStatus.RUNNING and stalled is False
