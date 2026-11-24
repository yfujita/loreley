"""ジョブの一覧・詳細(EP-09・10。C 5.2〜5.4・8.6。D 5.3)。

主たる読み取り(EP-09 のジョブ一覧、EP-10 のジョブ記録)が失敗すれば 503。付随する読み取り
(ロック文書・最新の `crawl` の ID・データソースの設定・削除結果)の失敗は 200 で、該当の項目を
`null` にして `unavailable` に理由を載せる。
"""

from collections.abc import Sequence
from datetime import datetime

from loreley_api.admin.base.codes import DeletionCurrentState, JobStatus, JobType
from loreley_api.admin.base.constants import PAGE_WINDOW_LIMIT
from loreley_api.admin.base.errors import job_not_found, unavailable
from loreley_api.admin.derivation import deletion_view, job_view, rerun
from loreley_api.admin.derivation.job_view import JobBriefView, read_job_brief
from loreley_api.admin.derivation.rerun import RerunDecision, SourceCondition, UndecidedBecause
from loreley_api.admin.failures import reason_of, row_unavailable, top_level_unavailable
from loreley_api.admin.schemas.jobs import (
    Deletion,
    DeletionCurrent,
    DeletionSettings,
    DeletionSummary,
    JobDetailResponse,
    JobListItem,
    JobListResponse,
    Registration,
)
from loreley_api.admin.services.job_brief import brief_fields
from loreley_api.admin.services.stalled_check import RunningJob, StalledCheck, StalledOutcome
from loreley_api.common.clock import Clock
from loreley_api.common.concurrency import CATEGORY_OPENSEARCH, BlockingRunner
from loreley_api.common.results import Failed
from loreley_api.common.timestamps import format_instant
from loreley_api.infrastructure.opensearch import (
    DeletionsReader,
    JobListQuery,
    JobsReader,
    PageRequest,
    SourcesReader,
    StoredRecord,
)
from loreley_api.infrastructure.opensearch.ports import JOB_BRIEF_FIELDS, JOB_DETAIL_FIELDS

# 再実行の判定に使うデータソースの設定の項目(状態だけ)。
SOURCE_STATUS_FIELDS = ("status",)


class JobQueryService:
    def __init__(
        self,
        *,
        jobs: JobsReader,
        sources: SourcesReader,
        deletions: DeletionsReader,
        stalled_check: StalledCheck,
        runner: BlockingRunner,
        clock: Clock,
    ) -> None:
        self._jobs = jobs
        self._sources = sources
        self._deletions = deletions
        self._stalled_check = stalled_check
        self._runner = runner
        self._clock = clock

    async def list_jobs(
        self,
        *,
        source_id: str | None,
        statuses: Sequence[JobStatus],
        page: int,
        items_per_page: int,
        descending: bool,
    ) -> JobListResponse:
        """EP-09。`statuses` が空なら絞り込まない。

        `page * items_per_page` が窓(10,000)以内であることは、呼び出し側(入力の検証)が保証する。
        """
        now = self._clock.now()
        query = JobListQuery(
            page=PageRequest(page, items_per_page, descending),
            source_id=source_id,
            statuses=tuple(status.value for status in statuses),
        )
        listed = await self._runner.run(CATEGORY_OPENSEARCH, self._jobs.list_jobs, query)
        if isinstance(listed, Failed):
            raise unavailable()

        briefs = [
            read_job_brief(record.record_id, record.source, fallback_source_id=source_id or "")
            for record in listed.value.items
        ]
        judged_jobs = await self._stalled_check.judge(briefs, job_fields=JOB_BRIEF_FIELDS, now=now)
        row_reasons = row_unavailable(
            [judged.brief.job_id for judged in judged_jobs],
            {
                judged.brief.job_id: {"stalled": reason_of(judged.failure)}
                for judged in judged_jobs
                if judged.failure is not None
            },
        )
        return JobListResponse(
            items=[
                JobListItem(
                    **brief_fields(judged.brief, judged.stalled),
                    unavailable=row_reasons[judged.brief.job_id],
                )
                for judged in judged_jobs
            ],
            total=listed.value.total,
            page=page,
            items_per_page=items_per_page,
            window_limit=PAGE_WINDOW_LIMIT,
            unavailable=top_level_unavailable({}),
        )

    async def get_job(self, job_id: str) -> JobDetailResponse:
        """EP-10。`job_id` は形式を検証済みで、`record_type=job` の記録がなければ 404。"""
        now = self._clock.now()
        records = await self._runner.run(
            CATEGORY_OPENSEARCH, self._jobs.get_jobs, [job_id], JOB_DETAIL_FIELDS
        )
        found = records[job_id]
        if isinstance(found, Failed):
            raise unavailable()
        if found.value is None:
            raise job_not_found()

        record = found.value
        brief = read_job_brief(record.record_id, record.source)
        # 取得できなかった項目のパス → 失敗(付随する読み取り。200 で `null` + `unavailable`)。
        failures: dict[str, Failed] = {}

        outcome = await self._check_stalled(brief, now)
        if outcome is not None:
            if outcome.refreshed_job is not None:
                record = outcome.refreshed_job
                brief = read_job_brief(record.record_id, record.source)
            if outcome.failure is not None:
                failures["stalled"] = outcome.failure
                failures["lease_expires_at"] = outcome.failure
        is_stalled = outcome.stalled if outcome is not None else False

        latest_for_source = await self._read_latest_for_source(brief, failures)
        source_condition, source_failure = await self._read_source_condition(brief)
        decision = rerun.decide_rerun(
            job_type=brief.job_type,
            status=brief.status,
            stalled=is_stalled,
            latest_for_source=latest_for_source,
            source=source_condition,
        )
        undecided_cause = _cause_of(decision, failures, source_failure)
        if undecided_cause is not None:
            failures["rerunnable"] = undecided_cause
        deletion = await self._read_deletion(brief, record, now, failures)

        return JobDetailResponse(
            **brief_fields(brief, is_stalled),
            failure_detail=job_view.read_failure_detail(record.source, brief.status),
            lease_expires_at=outcome.lease_expires_at if outcome is not None else None,
            latest_for_source=latest_for_source,
            rerunnable=decision.rerunnable,
            rerun_blocked_reason=decision.blocked_reason,
            cancel_after_finish_notice=rerun.has_cancel_after_finish_notice(
                brief.status, record.source
            ),
            warnings=job_view.read_warnings(record.source),
            registration=_registration_of(record, brief),
            deletion=deletion,
            unavailable=top_level_unavailable(
                {path: reason_of(failed) for path, failed in failures.items()}
            ),
        )

    async def _check_stalled(self, brief: JobBriefView, now: datetime) -> StalledOutcome | None:
        """`running` のジョブだけ判定する(それ以外は `stalled=false` で、読み取りをしない)。"""
        if brief.status is not JobStatus.RUNNING:
            return None
        outcomes = await self._stalled_check.check(
            [RunningJob(brief.job_id, brief.source_id)], job_fields=JOB_DETAIL_FIELDS, now=now
        )
        return outcomes[brief.job_id]

    async def _read_latest_for_source(
        self, brief: JobBriefView, failures: dict[str, Failed]
    ) -> bool | None:
        """`crawl` ジョブだけ、最新の `crawl` の ID を読んで比べる(それ以外は読まずに `false`)。"""
        if brief.job_type is not JobType.CRAWL:
            return False
        latest = await self._runner.run(
            CATEGORY_OPENSEARCH, self._jobs.latest_crawl_id, brief.source_id
        )
        if isinstance(latest, Failed):
            failures["latest_for_source"] = latest
            return None
        return rerun.is_latest_for_source(brief.job_type, brief.job_id, latest.value)

    async def _read_source_condition(
        self, brief: JobBriefView
    ) -> tuple[SourceCondition, Failed | None]:
        """データソースの設定の状態。C 5.3 の順 7〜10(`failed` の `crawl`)だけが使う。

        それ以外は、それより前の行で決まるので読まない(返す `ACTIVE` は使われない)。
        """
        if brief.job_type is not JobType.CRAWL or brief.status is not JobStatus.FAILED:
            return SourceCondition.ACTIVE, None
        result = await self._runner.run(
            CATEGORY_OPENSEARCH, self._sources.get, brief.source_id, SOURCE_STATUS_FIELDS
        )
        if isinstance(result, Failed):
            return SourceCondition.READ_FAILED, result
        source = result.value.source if result.value is not None else None
        return rerun.source_condition_of(source), None

    async def _read_deletion(
        self, brief: JobBriefView, record: StoredRecord, now: datetime, failures: dict[str, Failed]
    ) -> Deletion | None:
        """`crawl` ジョブの削除の状況。`source_delete`(と種別が読めないジョブ)は `null`。"""
        if brief.job_type is not JobType.CRAWL:
            return None
        summary = deletion_view.read_deletion_summary(record.source)
        settings = deletion_view.read_deletion_settings(record.source)

        # 実行待ちのジョブは読まない(削除はまだ始まっていない)。
        current: DeletionCurrent | None = None
        current_state = DeletionCurrentState.NOT_FOUND
        fetched_at: str | None = None
        if brief.status is not JobStatus.QUEUED:
            fetched_at = format_instant(now)
            result = await self._runner.run(
                CATEGORY_OPENSEARCH, self._deletions.get_result, brief.job_id
            )
            if isinstance(result, Failed):
                failures["deletion.current"] = result
                current_state = DeletionCurrentState.UNAVAILABLE
            elif result.value is not None:
                current_view = deletion_view.read_deletion_current(result.value.source)
                current = DeletionCurrent.model_validate(current_view, from_attributes=True)
                current_state = DeletionCurrentState.AVAILABLE

        return Deletion(
            summary=DeletionSummary.model_validate(summary, from_attributes=True)
            if summary is not None
            else None,
            confirmation=deletion_view.read_deletion_confirmation(record.source),
            current=current,
            current_state=current_state,
            fetched_at=fetched_at,
            settings=DeletionSettings.model_validate(settings, from_attributes=True)
            if settings is not None
            else None,
        )


def _cause_of(
    decision: RerunDecision, failures: dict[str, Failed], source_failure: Failed | None
) -> Failed | None:
    """`rerunnable=null` の原因になった読み取りの失敗(`unavailable.rerunnable` の理由の元)。"""
    match decision.undecided_because:
        case UndecidedBecause.STALLED:
            return failures.get("stalled")
        case UndecidedBecause.LATEST_FOR_SOURCE:
            return failures.get("latest_for_source")
        case UndecidedBecause.SOURCE:
            return source_failure
        case None:
            return None


def _registration_of(record: StoredRecord, brief: JobBriefView) -> Registration | None:
    registration = job_view.read_registration(record.source, brief.job_type, brief.status)
    if registration is None:
        return None
    return Registration.model_validate(registration, from_attributes=True)
