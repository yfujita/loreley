"""EP-09 `GET /jobs`・EP-10 `GET /jobs/{job_id}`(B 5.1・5.2)。

業務判断をしない。入力を検証し、サービスを呼んで DTO を返すだけ。
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from loreley_api.admin.base.codes import JobStatus, Reason
from loreley_api.admin.base.errors import FieldViolation, invalid_request
from loreley_api.admin.routers.request_input import (
    SOURCE_ID_PATTERN,
    JobIdPath,
    PageParams,
    read_paging,
    reject_unknown_query,
)
from loreley_api.admin.schemas.jobs import JobDetailResponse, JobListResponse
from loreley_api.admin.services.job_queries import JobQueryService

# 複合の絞り込み値(`queued` + `running`)。
ACTIVE_FILTER = "active"
ACTIVE_STATUSES = (JobStatus.QUEUED, JobStatus.RUNNING)
# 画面の「開始」列の並べ替えも `queued_at` に対応づける(直列実行のため受付の順と開始の順は一致する。
# B 5.1)。
DEFAULT_SORT = "-queued_at"

LIST_QUERY_NAMES = frozenset({"source_id", "status", "page", "items_per_page", "sort"})
NO_QUERY_NAMES: frozenset[str] = frozenset()


@dataclass(frozen=True)
class JobListFilters:
    source_id: str | None
    # 空なら絞り込まない。
    statuses: tuple[JobStatus, ...]


async def read_job_list_filters(
    source_id: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> JobListFilters:
    """`source_id`(2.12 の形式。登録されていない ID は 404 にせず空の結果)と `status`。"""
    violations: list[FieldViolation] = []
    if source_id is not None and SOURCE_ID_PATTERN.fullmatch(source_id) is None:
        violations.append(FieldViolation("source_id", Reason.FORMAT))
    statuses: tuple[JobStatus, ...] = ()
    if status == ACTIVE_FILTER:
        statuses = ACTIVE_STATUSES
    elif status is not None:
        try:
            statuses = (JobStatus(status),)
        except ValueError:
            violations.append(FieldViolation("status", Reason.UNSUPPORTED))
    if violations:
        raise invalid_request(violations)
    return JobListFilters(source_id, statuses)


JOB_PAGING = Depends(read_paging(sortable_fields={"queued_at"}, default_sort=DEFAULT_SORT))


def create_jobs_router(job_queries: JobQueryService) -> APIRouter:
    router = APIRouter()

    @router.get("/jobs", dependencies=[Depends(reject_unknown_query(LIST_QUERY_NAMES))])
    async def list_jobs(
        paging: Annotated[PageParams, JOB_PAGING],
        filters: Annotated[JobListFilters, Depends(read_job_list_filters)],
    ) -> JobListResponse:
        return await job_queries.list_jobs(
            source_id=filters.source_id,
            statuses=filters.statuses,
            page=paging.page,
            items_per_page=paging.items_per_page,
            descending=paging.descending,
        )

    @router.get("/jobs/{job_id}")
    async def get_job(
        job_id: JobIdPath,
        # 検証の順序は パス → クエリ(A 5.3)。引数の順で実行される。
        _query: Annotated[None, Depends(reject_unknown_query(NO_QUERY_NAMES))],
    ) -> JobDetailResponse:
        return await job_queries.get_job(job_id)

    return router
