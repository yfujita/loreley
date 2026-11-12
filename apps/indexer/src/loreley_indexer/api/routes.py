"""8 つの API と `/healthz` のエンドポイント(api 1章。パスとメソッドは設計書の案のとおり)。

形式の検証(`schemas`、`request_body`)と、ドメインの入力への変換、結果の整形(`responses`)だけを
行い、受理条件の判定や書き込みの判断はしない(R4)。ハンドラは同期 `def` で、FastAPI が
スレッドプールで実行する(plan 案9)。

`DELETE`(ソース削除 2・3)の `lock` は、ボディで運ぶ(api 3.2・4.7・4.8 は運び方を決めていない。
4.6 の例のボディ形式に揃えた)。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response

from loreley_indexer.api.batch import prepare_documents
from loreley_indexer.api.config import ApiConfig
from loreley_indexer.api.dependencies import ApiDependencies
from loreley_indexer.api.errors import InvalidRequestError
from loreley_indexer.api.request_body import parse_model, read_limited_body
from loreley_indexer.api.responses import (
    batch_response,
    last_seen_response,
    start_response,
    status_response,
)
from loreley_indexer.api.schemas import (
    BatchBody,
    DiscardBody,
    FinishBody,
    IdStr,
    LastSeenBody,
    LockedBody,
    StartBody,
)
from loreley_indexer.crawl_runs import FinishNotification, FinishOutcome, StartNotification
from loreley_indexer.documents import CrawlContext

SourceId = Annotated[IdStr, Path()]
CrawlId = Annotated[IdStr, Path()]


def build_router(*, dependencies: ApiDependencies, config: ApiConfig) -> APIRouter:
    router = APIRouter()

    async def read_body(request: Request) -> bytes:
        return await read_limited_body(request, max_bytes=config.max_request_body_bytes)

    RawBody = Annotated[bytes, Depends(read_body)]

    @router.get("/healthz", response_model=None)
    def healthz() -> dict[str, str]:
        # 起動時の整理が終わるまでは、ミドルウェアが 503 を返す(`middleware.py`)。
        # 内部情報(バージョン・設定・ログ)は出さない。
        return {"status": "ok"}

    @router.post("/crawls/start", response_model=None)
    def start_crawl(raw_body: RawBody) -> dict[str, str]:
        body = parse_model(StartBody, raw_body)
        dependencies.crawl_runs.start_crawl(
            StartNotification(
                crawl_id=body.crawl_id,
                source_id=body.source_id,
                crawl_started_at=body.crawl_started_at,
                ttl=body.ttl,
                ratio_threshold=body.ratio_threshold,
                min_delete_count=body.min_delete_count,
                force_delete=body.force_delete,
                rewrite_mode=body.rewrite_mode,
            )
        )
        return start_response(body.crawl_id)

    @router.post("/crawls/{crawl_id}/finish", response_model=None)
    def finish_crawl(crawl_id: CrawlId, raw_body: RawBody) -> Response:
        body = parse_model(FinishBody, raw_body)
        dependencies.crawl_runs.finish_crawl(
            FinishNotification(
                crawl_id=crawl_id,
                source_id=body.source_id,
                outcome=FinishOutcome(body.outcome),
                finished_at=body.finished_at,
                enumerated_count=body.enumerated_count,
                skipped_document_ids=body.skipped_document_ids,
                oversize_document_ids=body.oversize_document_ids,
            )
        )
        return Response(status_code=202)

    @router.get("/crawls/{crawl_id}", response_model=None)
    def crawl_status(crawl_id: CrawlId) -> dict[str, object]:
        return status_response(dependencies.crawl_runs.crawl_status(crawl_id))

    @router.post("/sources/{source_id}/documents:batch", response_model=None)
    def register_documents(source_id: SourceId, raw_body: RawBody) -> dict[str, object]:
        body = parse_model(BatchBody, raw_body)
        # 件数・サイズの防御は、デコードの前に行う(`prepare_documents`)。
        documents = prepare_documents(body.documents, config)
        context = CrawlContext(
            source_id=source_id,
            crawl_id=body.crawl_id,
            crawl_started_at=body.crawl_started_at,
            lock=body.lock.to_domain(),
        )
        return batch_response(dependencies.registrar.register(context, documents))

    @router.post("/sources/{source_id}/last-seen", response_model=None)
    def update_last_seen(source_id: SourceId, raw_body: RawBody) -> dict[str, object]:
        body = parse_model(LastSeenBody, raw_body)
        if len(body.document_ids) > config.max_last_seen_ids:
            raise InvalidRequestError("document_ids has too many items")
        context = CrawlContext(
            source_id=source_id,
            crawl_id=body.crawl_id,
            crawl_started_at=body.crawl_started_at,
            lock=body.lock.to_domain(),
        )
        return last_seen_response(dependencies.last_seen.update(context, body.document_ids))

    @router.post("/sources/{source_id}/deletions:discard", response_model=None)
    def discard_source_crawls(source_id: SourceId, raw_body: RawBody) -> dict[str, object]:
        body = parse_model(DiscardBody, raw_body)
        discarded = dependencies.deletion.discard_source_crawls(source_id, body.lock.to_domain())
        return {"discarded_crawl_ids": discarded}

    @router.delete("/sources/{source_id}/documents", response_model=None)
    def delete_source_documents(source_id: SourceId, raw_body: RawBody) -> dict[str, object]:
        body = parse_model(LockedBody, raw_body)
        deleted_count = dependencies.deletion.delete_source_documents(
            source_id, body.lock.to_domain()
        )
        return {"deleted_count": deleted_count}

    @router.delete("/sources/{source_id}/deletion-records", response_model=None)
    def delete_source_records(source_id: SourceId, raw_body: RawBody) -> dict[str, object]:
        body = parse_model(LockedBody, raw_body)
        deleted = dependencies.deletion.delete_source_records(source_id, body.lock.to_domain())
        return {"deleted": deleted}

    return router
