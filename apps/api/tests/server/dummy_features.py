"""機能パッケージの代役(テスト専用。製品コードには置かない)。

`create_app` の口(`routers`・`mounts`)に載せて、admin・search のような機能が載ったときの
共通の動き(エラー形式・アクセスログ・`no-store`・例外の吸収)を確かめる。
"""

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.types import Lifespan

from loreley_api.common.http import ApiError

SENTINEL_EXCEPTION = "SENTINEL-EXCEPTION-MESSAGE"
SENTINEL_ID = "SENTINEL-ITEM-ID"


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    count: int = Field(1, ge=1, le=10)


class DummyResource:
    """親の lifespan が開き、終了時に閉じる資源(クライアントの代役)。"""

    def __init__(self) -> None:
        self.is_open = False


def create_dummy_router(*, path_prefix: str = "") -> APIRouter:
    """サブアプリと外側に直接載せる両方で使える、典型的な失敗を起こすルート群。"""
    router = APIRouter(prefix=path_prefix)

    @router.get("/items/{item_id}")
    async def get_item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    @router.post("/items")
    async def create_item(item: Item) -> dict[str, str]:
        return {"name": item.name}

    @router.get("/api-error")
    async def raise_api_error() -> None:
        raise ApiError(409, "dummy_conflict", "the dummy is in conflict", retryable=True)

    @router.get("/teapot")
    async def raise_http_exception() -> None:
        raise HTTPException(418, detail=SENTINEL_EXCEPTION)

    @router.get("/boom")
    async def raise_unexpected_error() -> None:
        raise RuntimeError(SENTINEL_EXCEPTION)

    return router


def create_dummy_app(
    name: str,
    *,
    resource: DummyResource | None = None,
    lifespan: Lifespan[FastAPI] | None = None,
    redirect_slashes: bool = False,
) -> FastAPI:
    """サブアプリの代役。`name` は、どのサブアプリが応答したかを区別するため。"""
    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=redirect_slashes,
        lifespan=lifespan,
    )
    app.include_router(create_dummy_router())

    @app.get("/whoami")
    async def whoami() -> dict[str, str | bool]:
        # サブアプリの処理から、親の lifespan が用意した資源が使えることの確認用。
        body: dict[str, str | bool] = {"app": name}
        if resource is not None:
            body["resource_open"] = resource.is_open
        return body

    return app
