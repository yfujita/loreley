"""EP-01 `GET /sources`・EP-02 `GET /sources/{source_id}`(B 3.1・3.2)。

業務判断をしない。入力を検証し、サービスを呼んで DTO を返すだけ。登録・更新・削除・クロール操作
(POST・PUT・DELETE)は別のフェーズで足す。
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from loreley_api.admin.routers.request_input import SourceIdPath, reject_unknown_query
from loreley_api.admin.schemas.sources import SourceDetailResponse, SourceListResponse
from loreley_api.admin.services.source_catalog import SourceCatalogService

NO_QUERY_NAMES: frozenset[str] = frozenset()


def create_sources_router(source_catalog: SourceCatalogService) -> APIRouter:
    router = APIRouter()

    @router.get("/sources", dependencies=[Depends(reject_unknown_query(NO_QUERY_NAMES))])
    async def list_sources() -> SourceListResponse:
        return await source_catalog.list_sources()

    @router.get("/sources/{source_id}")
    async def get_source(
        source_id: SourceIdPath,
        # 検証の順序は パス → クエリ(A 5.3)。引数の順で実行される。
        _query: Annotated[None, Depends(reject_unknown_query(NO_QUERY_NAMES))],
    ) -> SourceDetailResponse:
        return await source_catalog.get_source(source_id)

    return router
