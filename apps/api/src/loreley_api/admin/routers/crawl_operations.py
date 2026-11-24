"""EP-06 クロールの起動・EP-07 ジョブの取消・EP-08 ロックの解放(B 4章)。

業務判断をしない。入力を検証し、サービスを呼んで DTO を返すだけ。検証の順序は
パス → クエリ → 本文(A 5.3)。EP-07・08 は本文を読まない(あっても無視する)。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from loreley_api.admin.base.codes import ApiTag, ErrorCode
from loreley_api.admin.routers.request_input import (
    JobIdPath,
    SourceIdPath,
    read_body_as,
    reject_any_query,
)
from loreley_api.admin.schemas.common import JobAccepted
from loreley_api.admin.schemas.errors import CRAWLER_RELAY_ERROR_CODES, error_responses
from loreley_api.admin.schemas.jobs import CancelJobResponse
from loreley_api.admin.schemas.request_bodies import json_request_body
from loreley_api.admin.schemas.sources import ReleaseLockResponse, StartCrawlBody
from loreley_api.admin.services.crawl_commands import CrawlCommandService

read_start_crawl_body = read_body_as(StartCrawlBody)


def create_crawl_operations_router(crawl_commands: CrawlCommandService) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/sources/{source_id}/crawl-jobs",
        status_code=202,
        tags=[ApiTag.SOURCES],
        responses=error_responses(
            ErrorCode.SOURCE_CONFIG_NOT_FOUND,
            ErrorCode.SOURCE_DELETING,
            ErrorCode.MAINTENANCE_ENABLED,
            ErrorCode.LOCK_HELD,
            *CRAWLER_RELAY_ERROR_CODES,
        ),
        # 本文は省略できる(省略と `{}` は同じ)。
        openapi_extra=json_request_body(StartCrawlBody, required=False),
    )
    async def start_crawl(
        source_id: SourceIdPath,
        _query: Annotated[None, Depends(reject_any_query)],
        # 本文なし・`{}` は、どちらも `force_delete=false`・`rewrite_mode=false`。
        body: Annotated[StartCrawlBody, Depends(read_start_crawl_body)],
    ) -> JobAccepted:
        return await crawl_commands.start_crawl(
            source_id, force_delete=body.force_delete, rewrite_mode=body.rewrite_mode
        )

    # 200(実行待ちを取り消した)または 202(実行中への取消要求の受付)は、Crawler のものを引き継ぐ。
    @router.post(
        "/jobs/{job_id}/cancel",
        # ジョブに対する操作なので、`sources` ではなく `jobs`(A 5.4)。
        tags=[ApiTag.JOBS],
        responses={
            202: {"model": CancelJobResponse, "description": "Cancellation requested"},
            **error_responses(
                ErrorCode.JOB_NOT_FOUND,
                ErrorCode.JOB_NOT_CANCELLABLE,
                ErrorCode.JOB_ALREADY_FINISHED,
                *CRAWLER_RELAY_ERROR_CODES,
            ),
        },
    )
    async def cancel_job(
        job_id: JobIdPath,
        _query: Annotated[None, Depends(reject_any_query)],
        response: Response,
    ) -> CancelJobResponse:
        cancelled = await crawl_commands.cancel(job_id)
        response.status_code = cancelled.status_code
        return cancelled.body

    @router.delete(
        "/sources/{source_id}/lock",
        tags=[ApiTag.SOURCES],
        responses=error_responses(ErrorCode.LOCK_IN_USE, *CRAWLER_RELAY_ERROR_CODES),
    )
    async def release_lock(
        source_id: SourceIdPath,
        _query: Annotated[None, Depends(reject_any_query)],
    ) -> ReleaseLockResponse:
        return await crawl_commands.release_lock(source_id)

    return router
