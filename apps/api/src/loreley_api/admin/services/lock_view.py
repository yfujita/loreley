"""ロック文書 → ジョブ記録 → `lock_state` の読み取りの共通手順(C 5.1。EP-02 と 409 の付随情報)。

**ロックから始め、ジョブ記録は `lock.job_id` で引く**(読む順序はロック文書 → ジョブ記録。
逆にすると、ロックの解放・ジョブの終了の途中を誤って `stalled` と判定する)。どちらも `mget`
(リアルタイム)で読むので、検索の遅れによる食い違いは出ない。
"""

from dataclasses import dataclass
from datetime import datetime

from loreley_api.admin.derivation.lock_state import (
    JobAbsent,
    JobFound,
    JobLookup,
    JobReadFailed,
    LockDerivation,
    derive_lock,
)
from loreley_api.admin.derivation.values import read_mapping, read_non_empty_str
from loreley_api.common.concurrency import CATEGORY_OPENSEARCH, BlockingRunner
from loreley_api.common.results import Failed
from loreley_api.infrastructure.opensearch import JobsReader
from loreley_api.infrastructure.opensearch.ports import JOB_BRIEF_FIELDS


@dataclass(frozen=True)
class LockReading:
    """ロック文書の読み取りが失敗したときだけ、`lock` が `None` で `failure` がある。

    EP-02 は `lock=null`(`unavailable.lock`)にし、409 の付随情報は `lock_state=unknown` にする
    だけで、ステータス・`existing_job` を変えない(C 4.6)。ジョブ記録の読み取りの失敗は、
    `lock_state=unknown` になる(`lock` はある)。
    """

    lock: LockDerivation | None
    failure: Failed | None


class LockViewService:
    def __init__(self, *, jobs: JobsReader, runner: BlockingRunner, grace_seconds: float) -> None:
        self._jobs = jobs
        self._runner = runner
        self._grace_seconds = grace_seconds

    async def read(self, source_id: str, *, now: datetime) -> LockReading:
        locks = await self._runner.run(CATEGORY_OPENSEARCH, self._jobs.get_locks, [source_id])
        lock_result = locks[source_id]
        if isinstance(lock_result, Failed):
            return LockReading(lock=None, failure=lock_result)

        lock_source = lock_result.value.source if lock_result.value is not None else None
        job = await self._read_job(lock_source)
        derivation = derive_lock(lock_source, job, now=now, grace_seconds=self._grace_seconds)
        return LockReading(lock=derivation, failure=None)

    async def _read_job(self, lock_source: object | None) -> JobLookup:
        """`job_id` が文字列で空でないときだけ、ジョブ記録を引く(それ以外は引かない)。"""
        lock = read_mapping(lock_source)
        job_id = read_non_empty_str(lock.get("job_id")) if lock is not None else None
        if job_id is None:
            return JobAbsent()
        records = await self._runner.run(
            CATEGORY_OPENSEARCH, self._jobs.get_jobs, [job_id], JOB_BRIEF_FIELDS
        )
        record = records[job_id]
        if isinstance(record, Failed):
            return JobReadFailed()
        if record.value is None:
            return JobAbsent()
        return JobFound(record.value.source)
