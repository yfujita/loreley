"""ロック文書とハートビート(module 4.4 の `locks/`)。

`loreley-jobs` に書くのは `records/` と `locks/` だけ(R7)。
`records/` と `locks/` は互いに依存しない(R6)。
"""

from loreley_crawler.jobs.locks.heartbeat import (
    EventTickWaiter,
    Heartbeat,
    HeartbeatSettings,
    TickWaiter,
)
from loreley_crawler.jobs.locks.lock_document import (
    ANCIENT,
    EXPIRED,
    LOCK_RECORD_TYPE,
    LockDocument,
    lock_record_id,
)
from loreley_crawler.jobs.locks.lock_store import (
    Acquired,
    AcquireResult,
    DeleteLockResult,
    LeaseResult,
    LeaseSet,
    LockChanged,
    LockDeleted,
    LockHeld,
    LockNotOwned,
    LockStore,
    NotReleased,
    Released,
    ReleaseResult,
)

__all__ = [
    "ANCIENT",
    "EXPIRED",
    "LOCK_RECORD_TYPE",
    "AcquireResult",
    "Acquired",
    "DeleteLockResult",
    "EventTickWaiter",
    "Heartbeat",
    "HeartbeatSettings",
    "LeaseResult",
    "LeaseSet",
    "LockChanged",
    "LockDeleted",
    "LockDocument",
    "LockHeld",
    "LockNotOwned",
    "LockStore",
    "NotReleased",
    "ReleaseResult",
    "Released",
    "TickWaiter",
    "lock_record_id",
]
