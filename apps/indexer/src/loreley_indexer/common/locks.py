"""ロック所有の純粋判定。

ロック文書の形式は設計書に未定義の仮定義(`owner`、`job_id`、`lease_expires_at`)。
Crawler の設計で形式が決まったら、この判定と `infrastructure/opensearch/jobs.py` の
パースだけを直す。
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LockInfo:
    """Crawler が書き込み要請に添える、ロック所有情報(api 3.2)。

    `documents`(登録・`last-seen`)と `crawl_runs`(ソース削除 2・3)が共有する。
    """

    owner: str
    job_id: str


@dataclass(frozen=True)
class LockRecord:
    owner: str
    job_id: str
    lease_expires_at: datetime


def is_lock_owned(lock: LockRecord | None, *, owner: str, job_id: str, now: datetime) -> bool:
    """`owner` と `job_id` が一致し、リースが期限内なら所有している。

    ロック文書なし・期限切れ・所有者不一致は、すべて「所有していない」(api 3.4)。
    """
    if lock is None:
        return False
    if lock.owner != owner or lock.job_id != job_id:
        return False
    return now < lock.lease_expires_at
