"""データソースの一覧・詳細(EP-01・02。C 5.5・5.8・8.6。D 5.8)。

主たる読み取り(EP-01 の `loreley-sources` の全件、EP-02 の設定)が失敗すれば 503。付随する読み取り
(最新ジョブ・ロック文書・登録文書数)の失敗は 200 で、該当の項目を `null` にして `unavailable` に
理由を載せる。EP-01 の失敗は、その読み取りが担う行にだけ付ける(1 回の読み取りが全行を担う
最新ジョブの検索・件数の集計の失敗は、全行に同じキーが付く)。
"""

import dataclasses
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from loreley_api.admin.base.codes import SourceStatus, UnavailableReason
from loreley_api.admin.base.errors import source_config_not_found, unavailable
from loreley_api.admin.derivation.job_view import JobBriefView, read_job_brief
from loreley_api.admin.derivation.lock_state import LockDerivation
from loreley_api.admin.derivation.settings_view import (
    SourceRowView,
    SourceSettingsView,
    read_source_row,
    read_source_settings,
)
from loreley_api.admin.derivation.source_summary import delete_job_of, last_completed_at_of
from loreley_api.admin.failures import reason_of, row_unavailable, top_level_unavailable
from loreley_api.admin.schemas.common import ExistingJob, JobBrief
from loreley_api.admin.schemas.sources import (
    IndexSummary,
    Lock,
    SourceDetailResponse,
    SourceListItem,
    SourceListResponse,
)
from loreley_api.admin.services.job_brief import job_brief
from loreley_api.admin.services.lock_view import LockViewService
from loreley_api.admin.services.stalled_check import JudgedJob, StalledCheck
from loreley_api.common.clock import Clock
from loreley_api.common.concurrency import CATEGORY_OPENSEARCH, BlockingRunner
from loreley_api.common.results import Failed, Result
from loreley_api.infrastructure.opensearch import (
    CountsReader,
    JobsReader,
    SearchIndexReader,
    SourceJobsSummary,
    SourcesReader,
    StoredRecord,
)
from loreley_api.infrastructure.opensearch.ports import JOB_BRIEF_FIELDS

type JobsSummaries = Result[dict[str, SourceJobsSummary]]


@dataclasses.dataclass(frozen=True)
class _SourceJobs:
    """あるソースの最新ジョブ(R-3 の結果から作る。C 5.5)。ジョブがなければ `None`。"""

    last_crawl: JobBriefView | None
    last_completed_at: str | None
    # ソースが `deleting` のときだけ値がある。
    delete_job: JobBriefView | None


@dataclasses.dataclass(frozen=True)
class _JudgedSourceJobs:
    """`stalled` の判定を終えた、あるソースの最新ジョブ。"""

    last_crawl: JudgedJob | None
    last_completed_at: str | None
    delete_job: JudgedJob | None


_NO_JOBS = _SourceJobs(last_crawl=None, last_completed_at=None, delete_job=None)


class SourceCatalogService:
    def __init__(
        self,
        *,
        sources: SourcesReader,
        jobs: JobsReader,
        search_index: SearchIndexReader,
        counts: CountsReader,
        lock_view: LockViewService,
        stalled_check: StalledCheck,
        runner: BlockingRunner,
        clock: Clock,
    ) -> None:
        self._sources = sources
        self._jobs = jobs
        self._search_index = search_index
        self._counts = counts
        self._lock_view = lock_view
        self._stalled_check = stalled_check
        self._runner = runner
        self._clock = clock

    async def list_sources(self) -> SourceListResponse:
        """EP-01。全件(`source_id` の昇順)。"""
        now = self._clock.now()
        listed = await self._runner.run(CATEGORY_OPENSEARCH, self._sources.list_all)
        if isinstance(listed, Failed):
            raise unavailable()

        rows = [read_source_row(record.record_id, record.source) for record in listed.value]
        if not rows:
            return SourceListResponse(items=[], unavailable=top_level_unavailable({}))
        source_ids = [row.source_id for row in rows]

        summaries = await self._runner.run(
            CATEGORY_OPENSEARCH, self._jobs.latest_by_source, source_ids
        )
        counts = await self._runner.run(
            CATEGORY_OPENSEARCH, self._search_index.count_by_source, source_ids
        )
        jobs_by_source = await self._judge_stalled(
            {row.source_id: _jobs_of(row.source_id, row.status, summaries) for row in rows}, now
        )

        reasons_by_source = {
            row.source_id: _job_reasons(row.status, summaries, jobs_by_source[row.source_id])
            for row in rows
        }
        if isinstance(counts, Failed):
            for reasons in reasons_by_source.values():
                reasons["document_count"] = reason_of(counts)
        row_reasons = row_unavailable(source_ids, reasons_by_source)

        return SourceListResponse(
            items=[
                _list_item_of(
                    row,
                    jobs_by_source[row.source_id],
                    document_count=None
                    if isinstance(counts, Failed)
                    else counts.value[row.source_id],
                    reasons=row_reasons[row.source_id],
                )
                for row in rows
            ],
            # 行に属さない項目がないので、常に `{}`。
            unavailable=top_level_unavailable({}),
        )

    async def get_source(self, source_id: str) -> SourceDetailResponse:
        """EP-02。`source_id` は形式を検証済みで、設定がなければ 404。"""
        now = self._clock.now()
        found = await self._runner.run(CATEGORY_OPENSEARCH, self._sources.get, source_id, None)
        if isinstance(found, Failed):
            # 現在値がないまま S4 が全置換しないよう、設定が取れなければ部分的な応答にしない。
            raise unavailable()
        if found.value is None:
            raise source_config_not_found()

        settings = read_source_settings(found.value.record_id, found.value.source)
        reasons: dict[str, UnavailableReason] = dict.fromkeys(
            settings.malformed, UnavailableReason.MALFORMED
        )

        lock = await self._read_lock(source_id, now, reasons)

        summaries = await self._runner.run(
            CATEGORY_OPENSEARCH, self._jobs.latest_by_source, [source_id]
        )
        jobs_by_source = await self._judge_stalled(
            {source_id: _jobs_of(source_id, settings.status, summaries)}, now
        )
        jobs = jobs_by_source[source_id]
        reasons.update(_job_reasons(settings.status, summaries, jobs))

        document_count = await self._read_document_count(source_id, reasons)

        return SourceDetailResponse(
            **_settings_fields(settings),
            lock=lock,
            last_crawl=_brief_of(jobs.last_crawl),
            last_completed_at=jobs.last_completed_at,
            delete_job=_brief_of(jobs.delete_job),
            index=IndexSummary(document_count=document_count),
            unavailable=top_level_unavailable(reasons),
        )

    async def _read_lock(
        self, source_id: str, now: datetime, reasons: dict[str, UnavailableReason]
    ) -> Lock | None:
        reading = await self._lock_view.read(source_id, now=now)
        if reading.lock is not None:
            return _lock_of(reading.lock)
        # ロック文書の読み取りの失敗(`lock` がないのはこのときだけ)。
        if reading.failure is not None:
            reasons["lock"] = reason_of(reading.failure)
        return None

    async def _read_document_count(
        self, source_id: str, reasons: dict[str, UnavailableReason]
    ) -> int | None:
        results = await self._runner.run(
            CATEGORY_OPENSEARCH, self._counts.count_for_source, source_id, ["document_count"]
        )
        count = results["document_count"]
        if isinstance(count, Failed):
            reasons["index.document_count"] = reason_of(count)
            return None
        return count.value

    async def _judge_stalled(
        self, jobs_by_source: Mapping[str, _SourceJobs], now: datetime
    ) -> dict[str, _JudgedSourceJobs]:
        """`running` のジョブだけ `stalled` を判定する(ロック文書は対象のソースをまとめて読む)。"""
        briefs = [
            brief
            for jobs in jobs_by_source.values()
            for brief in (jobs.last_crawl, jobs.delete_job)
            if brief is not None
        ]
        judged = await self._stalled_check.judge(briefs, job_fields=JOB_BRIEF_FIELDS, now=now)
        judged_by_job_id = {judged_job.brief.job_id: judged_job for judged_job in judged}

        def pick(brief: JobBriefView | None) -> JudgedJob | None:
            return judged_by_job_id[brief.job_id] if brief is not None else None

        return {
            source_id: _JudgedSourceJobs(
                last_crawl=pick(jobs.last_crawl),
                last_completed_at=jobs.last_completed_at,
                delete_job=pick(jobs.delete_job),
            )
            for source_id, jobs in jobs_by_source.items()
        }


def _jobs_of(source_id: str, status: SourceStatus | None, summaries: JobsSummaries) -> _SourceJobs:
    """R-3 の結果から、あるソースの最新ジョブを作る。失敗(`Failed`)のときは値がない扱い。"""
    if isinstance(summaries, Failed):
        return _NO_JOBS
    summary = summaries.value.get(source_id)
    if summary is None:
        return _NO_JOBS
    return _SourceJobs(
        last_crawl=_job_view_of(source_id, summary.latest_crawl),
        last_completed_at=last_completed_at_of(summary.last_completed_epoch_millis),
        delete_job=_job_view_of(source_id, delete_job_of(status, summary.latest_source_delete)),
    )


def _job_view_of(source_id: str, record: StoredRecord | None) -> JobBriefView | None:
    if record is None:
        return None
    return read_job_brief(record.record_id, record.source, fallback_source_id=source_id)


def _job_reasons(
    status: SourceStatus | None, summaries: JobsSummaries, jobs: _JudgedSourceJobs
) -> dict[str, UnavailableReason]:
    """最新ジョブに関する失敗(C 5.8)。EP-01 は行の相対パス、EP-02 は最上位の正式なパスと同じ。"""
    reasons: dict[str, UnavailableReason] = {}
    if isinstance(summaries, Failed):
        reason = reason_of(summaries)
        reasons["last_crawl"] = reason
        reasons["last_completed_at"] = reason
        # `active` のソースは `delete_job` が常に `null`(値がない)なので、キーを付けない。
        if status is SourceStatus.DELETING:
            reasons["delete_job"] = reason
    if jobs.last_crawl is not None and jobs.last_crawl.failure is not None:
        reasons["last_crawl.stalled"] = reason_of(jobs.last_crawl.failure)
    if jobs.delete_job is not None and jobs.delete_job.failure is not None:
        reasons["delete_job.stalled"] = reason_of(jobs.delete_job.failure)
    return reasons


def _list_item_of(
    row: SourceRowView,
    jobs: _JudgedSourceJobs,
    *,
    document_count: int | None,
    reasons: dict[str, UnavailableReason],
) -> SourceListItem:
    return SourceListItem(
        source_id=row.source_id,
        connector_type=row.connector_type,
        schedule_cron=row.schedule_cron,
        status=row.status,
        last_crawl=_brief_of(jobs.last_crawl),
        last_completed_at=jobs.last_completed_at,
        delete_job=_brief_of(jobs.delete_job),
        document_count=document_count,
        unavailable=reasons,
    )


def _brief_of(judged: JudgedJob | None) -> JobBrief | None:
    if judged is None:
        return None
    return job_brief(judged.brief, judged.stalled)


def _lock_of(lock: LockDerivation) -> Lock:
    job = ExistingJob.model_validate(lock.job, from_attributes=True) if lock.job else None
    return Lock(state=lock.state, job=job, acquired_at=lock.acquired_at)


def _settings_fields(settings: SourceSettingsView) -> dict[str, Any]:
    """`SourceSettings` の項目(`malformed` は `unavailable` に載るので応答の項目ではない)。"""
    fields = dataclasses.asdict(settings)
    del fields["malformed"]
    return fields
