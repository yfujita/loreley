"""EP-12 `GET /opensearch/cluster`(B 7.1)。パラメーターはない(絞り込み・並べ替えは画面側)。"""

from fastapi import APIRouter, Depends

from loreley_api.admin.base.codes import ApiTag, ErrorCode
from loreley_api.admin.routers.request_input import reject_any_query
from loreley_api.admin.schemas.errors import error_responses
from loreley_api.admin.schemas.opensearch import ClusterResponse
from loreley_api.admin.services.cluster_overview import ClusterOverviewService


def create_opensearch_router(cluster_overview: ClusterOverviewService) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/opensearch/cluster",
        tags=[ApiTag.OPENSEARCH],
        responses=error_responses(ErrorCode.UNAVAILABLE),
        dependencies=[Depends(reject_any_query)],
    )
    async def get_cluster() -> ClusterResponse:
        return await cluster_overview.get_cluster()

    return router
