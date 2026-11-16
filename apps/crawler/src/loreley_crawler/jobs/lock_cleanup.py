"""版条件つきのロック文書の削除と、競合したときの読み直し(architecture 5.5)。

受付の巻き戻し・`queued` の取り消し・起動時の回復が使う。対象のロックを判断した後、読んだ版を
条件に消す。条件が外れたら(ハートビートなどで版が進んだ)読み直し、まだ対象のロックなら新しい
版で消し、なくなっていれば完了、他のジョブのロックになっていれば何もしない。
1 回ごとの Store 層の呼び出しは、呼び出し側が `Retrier` で包む(全体の異常のリトライ)。
応答が失われた削除のリトライは、ロックがなくなっているので完了になる。
"""

from collections.abc import Callable

from loreley_crawler.common.conflict import MAX_CONFLICT_ATTEMPTS
from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.jobs.locks import LockDeleted, LockDocument, LockStore


def delete_lock_unless_taken_over(
    lock_store: LockStore,
    lock: LockDocument,
    *,
    is_target: Callable[[LockDocument], bool],
) -> bool:
    """`lock` を消す。ロックがなくなったら True、`is_target` が偽のロックになっていたら False。

    `is_target` は、読み直したロックが、消してよい対象かの判断(例: 自分の `job_id` のロック)。
    繰り返しても競合が解けなければ `StoreUnavailableError`。
    """
    current = lock
    for _ in range(MAX_CONFLICT_ATTEMPTS):
        if isinstance(lock_store.delete_unchanged(current), LockDeleted):
            return True
        reread = lock_store.read(lock.source_id)
        if reread is None:
            return True
        if not is_target(reread):
            return False
        current = reread
    raise StoreUnavailableError("lock_cleanup_contention")
