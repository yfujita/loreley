"""EP-01〜05(B 3章): 一覧・詳細・登録・更新・削除ジョブの起動。

業務判断をしない。入力を検証し、サービスを呼んで DTO を返すだけ。検証の順序は
パス → クエリ → 本文(A 5.3)で、引数と `dependencies` の順で実行される。
クロールの起動・ロックの解放(EP-06・08)は `crawl_operations.py`。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from loreley_api.admin.routers.request_input import SourceIdPath, read_body_as, reject_any_query
from loreley_api.admin.schemas.common import JobAccepted, SourceSettings
from loreley_api.admin.schemas.sources import (
    RegisterSourceBody,
    SourceDetailResponse,
    SourceListResponse,
    UpdateSourceBody,
)
from loreley_api.admin.services.source_catalog import SourceCatalogService
from loreley_api.admin.services.source_commands import SourceCommandService

read_register_body = read_body_as(RegisterSourceBody)
read_update_body = read_body_as(UpdateSourceBody)


def create_sources_router(
    source_catalog: SourceCatalogService, source_commands: SourceCommandService
) -> APIRouter:
    router = APIRouter()

    @router.get("/sources", dependencies=[Depends(reject_any_query)])
    async def list_sources() -> SourceListResponse:
        return await source_catalog.list_sources()

    @router.get("/sources/{source_id}")
    async def get_source(
        source_id: SourceIdPath,
        _query: Annotated[None, Depends(reject_any_query)],
    ) -> SourceDetailResponse:
        return await source_catalog.get_source(source_id)

    # 201(新規)。同じ内容がすでに登録されていたときは、Crawler の 200 を引き継ぐ。
    @router.post("/sources", status_code=201, dependencies=[Depends(reject_any_query)])
    async def register_source(
        body: Annotated[RegisterSourceBody, Depends(read_register_body)], response: Response
    ) -> SourceSettings:
        written = await source_commands.register(body)
        response.status_code = written.status_code
        return written.body

    @router.put("/sources/{source_id}")
    async def update_source(
        source_id: SourceIdPath,
        _query: Annotated[None, Depends(reject_any_query)],
        body: Annotated[UpdateSourceBody, Depends(read_update_body)],
    ) -> SourceSettings:
        written = await source_commands.update(source_id, body)
        return written.body

    @router.post("/sources/{source_id}/delete-jobs", status_code=202)
    async def start_source_delete(
        source_id: SourceIdPath,
        _query: Annotated[None, Depends(reject_any_query)],
    ) -> JobAccepted:
        return await source_commands.start_delete(source_id)

    return router
