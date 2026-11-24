"""EP-14 `GET /meta`(B 8.2)。設定だけで応答する。"""

from fastapi import APIRouter, Depends

from loreley_api.admin.base.codes import ApiTag
from loreley_api.admin.routers.request_input import reject_any_query
from loreley_api.admin.schemas.errors import error_responses
from loreley_api.admin.schemas.meta import MetaResponse
from loreley_api.admin.services.meta import MetaService


def create_meta_router(meta: MetaService) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/meta",
        tags=[ApiTag.META],
        responses=error_responses(),
        dependencies=[Depends(reject_any_query)],
    )
    async def get_meta() -> MetaResponse:
        return await meta.get_meta()

    return router
