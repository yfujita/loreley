"""EP-13 `GET /dashboard`(B 8.1)。

パス・クエリ・本文から何も受け取らない(確認先は設定だけで決まる。C 6.4)。各コンポーネントの
失敗は `components[].state` で表すので、`api` が応答できる限り 200。
"""

from fastapi import APIRouter, Depends

from loreley_api.admin.base.codes import ApiTag
from loreley_api.admin.routers.request_input import reject_any_query
from loreley_api.admin.schemas.dashboard import DashboardResponse
from loreley_api.admin.schemas.errors import error_responses
from loreley_api.admin.services.dashboard import DashboardService


def create_dashboard_router(dashboard: DashboardService) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/dashboard",
        tags=[ApiTag.DASHBOARD],
        # 各コンポーネントの失敗は 200 の `components[].state` で表す。400 は未知のクエリだけ。
        responses=error_responses(),
        dependencies=[Depends(reject_any_query)],
    )
    async def get_dashboard() -> DashboardResponse:
        return await dashboard.check_components()

    return router
