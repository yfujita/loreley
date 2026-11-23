"""EP-14 `GET /meta`(B 8.2)。設定だけで応答する。"""

from fastapi import APIRouter, Depends

from loreley_api.admin.routers.request_input import reject_unknown_query
from loreley_api.admin.schemas.meta import MetaResponse
from loreley_api.admin.services.meta import MetaService


def create_meta_router(meta: MetaService) -> APIRouter:
    router = APIRouter()

    @router.get("/meta", dependencies=[Depends(reject_unknown_query(frozenset()))])
    async def get_meta() -> MetaResponse:
        return await meta.get_meta()

    return router
