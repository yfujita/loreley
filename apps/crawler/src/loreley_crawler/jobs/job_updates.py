"""ジョブ記録の版条件つき更新と、競合したときの読み直し(architecture 5.3 の書き手の表。CA-P-43)。

ジョブ記録は、Job Runner と API 側(取り消し・ロック解放)が書くので、すべての更新は読んだ版を
条件にする。条件が外れたら記録を読み直し、「いまの状態でも、この更新を当てはめてよいか」を
判定し直す。当てはめてよい(`applicable_statuses` のどれか)なら、読み直した版でやり直す。
そうでなければ(状態が変わった・記録が消えた)、更新せずに読み直した記録を返す。
呼び出し側が、それを所有権の喪失・取り消し負け・何もしないのどれにするかを決める。

Store 層の全体の異常(`StoreUnavailableError`)は、操作ごとに `retrier` でリトライする。応答が
失われた書き込みのリトライは、`JobRecordStore.update` が、読み直した内容が自分の書いた内容と
一致すれば成功にする。
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any

from loreley_crawler.common.conflict import MAX_CONFLICT_ATTEMPTS
from loreley_crawler.common.errors import StoreUnavailableError, is_store_unavailable
from loreley_crawler.common.retry import Retrier
from loreley_crawler.jobs.records import (
    JobRecord,
    JobRecordStore,
    JobStatus,
    JobUpdated,
)


@dataclass(frozen=True)
class Applied:
    """更新した。`record` は新しい版つきの記録。"""

    record: JobRecord


@dataclass(frozen=True)
class NotApplicable:
    """読み直した記録の状態が、更新を当てはめてよい状態ではなかった(更新していない)。

    `current` は読み直した記録。記録が消えていれば None。
    """

    current: JobRecord | None


def apply_job_update(
    job_store: JobRecordStore,
    retrier: Retrier,
    record: JobRecord,
    changes: Mapping[str, Any],
    *,
    applicable_statuses: Collection[JobStatus],
) -> Applied | NotApplicable:
    target = record
    for _ in range(MAX_CONFLICT_ATTEMPTS):
        result = retrier.run(
            partial(job_store.update, target, changes), is_retryable_error=is_store_unavailable
        )
        if isinstance(result, JobUpdated):
            return Applied(result.record)
        current = result.current
        if current is None or current.status not in applicable_statuses:
            return NotApplicable(current)
        target = current
    raise StoreUnavailableError("job_update_contention")
