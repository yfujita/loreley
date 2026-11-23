"""`stalled` の確認読みの共通手順(C 5.2。EP-01・09・10 で共有する)。

一覧では、どの行が `running` か(どのロックを読むべきか)がジョブを読むまで分からないので、ロックを
先に読めない。ジョブを検索で読む(最大約 1 秒古い)間にジョブが終了してロックが消えていると、
ロックなしの `running` に見えて偽陽性になる。そこで、ロックの不一致を見たときに、**ロック → ジョブ
の順で新しく読み直す**。ジョブは `running` → 終端の順にしか変わらず、ロックはジョブの最終状態の
記録の後にしか消えないので、読み直しで `running` かつロックなしなら本当に止まっている。
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from loreley_api.admin.base.codes import JobStatus
from loreley_api.admin.derivation.job_view import JobBriefView, read_job_brief
from loreley_api.admin.derivation.stalled import judge_by_lock
from loreley_api.admin.derivation.values import read_choice
from loreley_api.common.concurrency import CATEGORY_OPENSEARCH, BlockingRunner
from loreley_api.common.results import Failed, Result
from loreley_api.infrastructure.opensearch import JobsReader, StoredRecord


@dataclass(frozen=True)
class RunningJob:
    """`status=running` と読めたジョブ。"""

    job_id: str
    source_id: str


@dataclass(frozen=True)
class StalledOutcome:
    # 判定できないとき(読み取りの失敗)だけ `None`。
    stalled: bool | None
    # EP-10 の `lease_expires_at`。ロック文書が一致し、日時として読めるときだけ値がある。
    lease_expires_at: str | None = None
    # `stalled` が `None` の原因(行・最上位の `unavailable` の理由コードの元)。
    failure: Failed | None = None
    # 確認読みで読み直したジョブ記録。ジョブが終わっていたときに、行の `status` などを読み直した値
    # にそろえるために、呼び出し側が使う。確認読みをしなかったときは `None`。
    refreshed_job: StoredRecord | None = None


@dataclass(frozen=True)
class JudgedJob:
    """`stalled` の判定を終えたジョブ。判定できなければ `stalled` は `None`、`failure` が原因。"""

    brief: JobBriefView
    stalled: bool | None
    failure: Failed | None


def apply_outcome(brief: JobBriefView, outcome: StalledOutcome | None) -> JudgedJob:
    """`outcome` が `None` のジョブは `running` でないので、`stalled=false`(読んでいない)。"""
    if outcome is None:
        return JudgedJob(brief, stalled=False, failure=None)
    # 確認読みで読み直したジョブがあれば、`status` などもその値にそろえる(終わったジョブを
    # `running` のまま見せない)。
    refreshed = outcome.refreshed_job
    if refreshed is not None:
        brief = read_job_brief(
            refreshed.record_id, refreshed.source, fallback_source_id=brief.source_id
        )
    return JudgedJob(brief, outcome.stalled, outcome.failure)


class StalledCheck:
    def __init__(self, *, jobs: JobsReader, runner: BlockingRunner) -> None:
        self._jobs = jobs
        self._runner = runner

    async def check(
        self,
        running_jobs: Sequence[RunningJob],
        *,
        job_fields: Sequence[str],
        now: datetime,
    ) -> dict[str, StalledOutcome]:
        """`running_jobs` の `stalled` を判定する。キーは `job_id`。

        ロック文書は、対象のソースをまとめて 1 回の `mget` で読む。文書単位の失敗は、そのソースの
        ジョブだけが `stalled=None` になり、他のジョブは影響を受けない。`mget` 全体の失敗は
        すべてのジョブが同じ失敗になる。`job_fields` は、確認読みでジョブ記録を読み直す項目。
        """
        if not running_jobs:
            return {}
        outcomes: dict[str, StalledOutcome] = {}
        unconfirmed_jobs: list[RunningJob] = []
        locks = await self._read_locks(running_jobs)
        for job in running_jobs:
            lock = locks[job.source_id]
            if isinstance(lock, Failed):
                outcomes[job.job_id] = StalledOutcome(stalled=None, failure=lock)
                continue
            judgement = judge_by_lock(_source_of(lock.value), job.job_id, now)
            if judgement is None:
                unconfirmed_jobs.append(job)
                continue
            outcomes[job.job_id] = StalledOutcome(judgement.stalled, judgement.lease_expires_at)
        if unconfirmed_jobs:
            outcomes.update(await self._confirm(unconfirmed_jobs, job_fields, now))
        return outcomes

    async def judge(
        self, briefs: Sequence[JobBriefView], *, job_fields: Sequence[str], now: datetime
    ) -> list[JudgedJob]:
        """`briefs` のうち `running` のものだけ `check` で判定する。結果は入力と同じ順。"""
        running_jobs = [
            RunningJob(brief.job_id, brief.source_id)
            for brief in briefs
            if brief.status is JobStatus.RUNNING
        ]
        outcomes = await self.check(running_jobs, job_fields=job_fields, now=now)
        return [apply_outcome(brief, outcomes.get(brief.job_id)) for brief in briefs]

    async def _confirm(
        self, jobs: Sequence[RunningJob], job_fields: Sequence[str], now: datetime
    ) -> dict[str, StalledOutcome]:
        """確認読み: ロック文書 → ジョブ記録の順に 1 回読み直す(順序を入れ替えない)。"""
        locks = await self._read_locks(jobs)
        job_ids = [job.job_id for job in jobs]
        records = await self._runner.run(
            CATEGORY_OPENSEARCH, self._jobs.get_jobs, job_ids, job_fields
        )
        return {
            job.job_id: _judge_after_confirmation(
                job.job_id, locks[job.source_id], records[job.job_id], now
            )
            for job in jobs
        }

    async def _read_locks(
        self, jobs: Sequence[RunningJob]
    ) -> dict[str, Result[StoredRecord | None]]:
        source_ids = list(dict.fromkeys(job.source_id for job in jobs))
        return await self._runner.run(CATEGORY_OPENSEARCH, self._jobs.get_locks, source_ids)


def _judge_after_confirmation(
    job_id: str,
    lock: Result[StoredRecord | None],
    record: Result[StoredRecord | None],
    now: datetime,
) -> StalledOutcome:
    """読み直した結果で決める(C 5.2 の手順 3)。読み取りが失敗したら判定できない(`None`)。"""
    if isinstance(lock, Failed):
        return StalledOutcome(stalled=None, failure=lock)
    if isinstance(record, Failed):
        return StalledOutcome(stalled=None, failure=record)

    refreshed_job = record.value
    # (a) もう `running` でなければ `false`。ジョブ記録が読み直しでなくなっていた場合も、判定する
    # 対象がないので `false` にする。
    if refreshed_job is None or _status_of(refreshed_job) is not JobStatus.RUNNING:
        return StalledOutcome(stalled=False, refreshed_job=refreshed_job)
    # (b) ロックが一致するようになっていれば、そのロックで判定する。
    judgement = judge_by_lock(_source_of(lock.value), job_id, now)
    if judgement is not None:
        return StalledOutcome(
            judgement.stalled, judgement.lease_expires_at, refreshed_job=refreshed_job
        )
    # (c) ロックが一致せず、ジョブはまだ `running`。本当に止まっている。
    return StalledOutcome(stalled=True, refreshed_job=refreshed_job)


def _status_of(record: StoredRecord) -> JobStatus | None:
    return read_choice(record.source.get("status"), JobStatus)


def _source_of(record: StoredRecord | None) -> Mapping[str, object] | None:
    return record.source if record is not None else None
