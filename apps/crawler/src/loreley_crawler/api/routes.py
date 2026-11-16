"""6 つのエンドポイントと `/healthz`(crawler-api 1章・4.7。パスとメソッドは設計書の案のとおり)。

形式の検証(`request_parsing`)、担当機能(`jobs`・`sources`)の呼び出し、結果の応答(`responses`)
だけを行い、受付の判断や書き込みの判断はしない(R4)。ハンドラは同期 `def` で、FastAPI が
スレッドプールで実行する(module 2.2)。`/healthz` を含め、リクエストのボディは必要なものだけ読む。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from loreley_crawler.api import responses
from loreley_crawler.api.dependencies import ApiDependencies
from loreley_crawler.api.request_body import read_limited_body
from loreley_crawler.api.request_parsing import (
    check_connector_config,
    check_job_id_path,
    check_source_id_path,
    parse_crawl_options,
    parse_new_source,
    parse_source_update,
)
from loreley_crawler.common.errors import is_store_unavailable


async def _read_body(request: Request) -> bytes:
    return await read_limited_body(request)


RawBody = Annotated[bytes, Depends(_read_body)]


def build_router(dependencies: ApiDependencies) -> APIRouter:
    router = APIRouter()
    deps = dependencies

    @router.get("/healthz", response_model=None)
    def healthz() -> dict[str, str]:
        """ヘルスチェック(契約外の運用用 API。案: CAPI-P-19・CM-P-27)。

        担当機能(`jobs`・`sources`)を呼ばない。応答できる = HTTP の受付が始まっている(起動時の
        回復の後)ことだけを示す。内部情報(版・設定・ジョブの状態)は返さない。
        """
        return {"status": "ok"}

    @router.post("/sources/{source_id}/crawl-jobs", response_model=None)
    def start_crawl(source_id: str, raw_body: RawBody) -> JSONResponse:
        check_source_id_path(source_id)
        options = parse_crawl_options(raw_body)
        result = deps.job_admission.accept_manual_crawl(
            source_id, force_delete=options.force_delete, rewrite_mode=options.rewrite_mode
        )
        return responses.admission_response(result)

    @router.post("/sources/{source_id}/delete-jobs", response_model=None)
    def start_source_delete(source_id: str) -> JSONResponse:
        check_source_id_path(source_id)
        return responses.admission_response(deps.job_admission.accept_source_delete(source_id))

    @router.post("/jobs/{job_id}/cancel", response_model=None)
    def cancel_job(job_id: str) -> JSONResponse:
        check_job_id_path(job_id)
        return responses.cancel_response(deps.job_cancellation.cancel(job_id))

    @router.delete("/sources/{source_id}/lock", response_model=None)
    def release_lock(source_id: str) -> JSONResponse:
        check_source_id_path(source_id)
        return responses.release_lock_response(source_id, deps.lock_release.release(source_id))

    @router.post("/sources", response_model=None)
    def register_source(raw_body: RawBody) -> JSONResponse:
        new_source = parse_new_source(raw_body, deps.connector_registry)
        check_connector_config(
            deps.connector_registry, new_source.connector_type, new_source.settings.connector_config
        )
        return responses.registration_response(deps.source_store.register(new_source))

    @router.put("/sources/{source_id}", response_model=None)
    def update_source(source_id: str, raw_body: RawBody) -> JSONResponse:
        check_source_id_path(source_id)
        settings = parse_source_update(raw_body, deps.connector_registry)
        # `connector_type` は登録後に変わらない。保存済みの値で `connector_config` を検証する。
        # 設定がない・種別が読めないときは検証できないので、`update` の結果(404・409・500)に任せる。
        stored = deps.retrier.run(
            lambda: deps.source_store.fetch(source_id), is_retryable_error=is_store_unavailable
        )
        if stored is not None and stored.connector_type is not None:
            check_connector_config(
                deps.connector_registry, stored.connector_type, settings.connector_config
            )
        return responses.update_response(deps.source_store.update(source_id, settings))

    return router
