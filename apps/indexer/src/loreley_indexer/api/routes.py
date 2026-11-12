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
        """ヘルスチェック。

        GET /healthz(運用用。Crawler・Admin API の契約には含めない)
        - 応答: 200 `{"status": "ok"}`
        - 起動時の整理が終わるまでは 503 `unavailable`(外からは接続拒否に見える)
        """
        # 起動時の整理が終わるまでは、ミドルウェアが 503 を返す(`middleware.py`)。
        # 内部情報(バージョン・設定・ログ)は出さない。
        return {"status": "ok"}

    @router.post("/crawls/start", response_model=None)
    def start_crawl(raw_body: RawBody) -> dict[str, str]:
        """開始通知(api 4.1)。クロールの開始を伝える。

        POST /crawls/start(呼び出し元: Crawler。ロック取得後・列挙の前)
        - リクエスト: `crawl_id`・`source_id`・`crawl_started_at`、設定スナップショット
          (`ttl`・`ratio_threshold`・`min_delete_count`)、任意で `force_delete`・`rewrite_mode`
          (どちらも既定 false)
        - 動作: そのソースの現行世代を更新し、削除結果(`running`)を作る。
          旧い未終了のクロールは `discarded`(`superseded`)にする
        - 応答: 200 `{"crawl_id", "status": "running"}`
        - 冪等: 同じ `crawl_id` で内容が一致する再送は成功。不一致は 409 `crawl_start_conflict`
        - エラー: 409 `crawl_already_finished`(終了済み)/`stale_crawl_started_at`(世代が古い)、
          503 `unavailable`
        """
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
        """終了通知(api 4.4)。列挙の終了を伝え、削除の判断・実行を非同期に起動する。

        POST /crawls/{crawl_id}/finish(呼び出し元: Crawler。登録・last-seen の応答を確認した後)
        - リクエスト: `source_id`、`outcome`(`enumeration_completed`/`failed`/`cancelled`)、
          `finished_at`。`enumeration_completed` では `enumerated_count`・`skipped_document_ids`・
          `oversize_document_ids` が必須
        - 応答: 202(ボディなし)。削除の判断結果は含めず、`GET /crawls/{crawl_id}` で確認する
        - 冪等: 同じ内容の再送は 202。内容が異なれば 409 `finish_content_mismatch`、
          `source_id` が合わなければ 409 `finish_source_mismatch`
        """
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
        """Status API(api 4.5)。削除結果を読み取りで返す。

        GET /crawls/{crawl_id}(呼び出し元: Crawler。終了通知後にポーリングする)
        - 応答: 200。`crawl_id`・`source_id`・`status`・`reason`・件数類・各時刻など
          (値のない項目はキーごと省く)
        - エラー: 404 `crawl_not_found`
        - 副作用なし
        """
        return status_response(dependencies.crawl_runs.crawl_status(crawl_id))

    @router.post("/sources/{source_id}/documents:batch", response_model=None)
    def register_documents(source_id: SourceId, raw_body: RawBody) -> dict[str, object]:
        """バッチ登録(api 4.3)。文書を同期で抽出・登録し、文書単位の結果を返す。

        POST /sources/{source_id}/documents:batch(呼び出し元: Crawler)
        - リクエスト: `crawl_id`・`crawl_started_at`・`lock`(`owner`・`job_id`)・`documents`
          (`external_id`・`title`・`mime_type`・`raw_content`(base64)・`content_hash`・
          `source_updated_at`・`size`、任意で `url`・`path`)
        - 応答: 200 `{"results": [...]}`。文書ごとに `status: ok`(`change` は
          created/updated/unchanged、`extract_failed`)または `status: failed`(`failure_type`)
        - 受理条件(削除結果が `running` で終了通知前、ロック所有)を満たさなければ全体を 409 で拒否。
          ロックの不所有は文書単位の `lock_not_owned`
        - 冪等: 変更のない文書は書き込まない。失敗した文書だけを再送できる
        - エラー: 400(形式不正・件数/サイズ超過)、409(受理条件)、503
        """
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
        """last_seen_at の部分更新(api 4.2)。列挙で見つけた文書の `last_seen_at` を更新する。

        POST /sources/{source_id}/last-seen(呼び出し元: Crawler。文書の取得より前)
        - リクエスト: `crawl_id`・`crawl_started_at`・`lock`・`document_ids`(Crawler が算出した
          document_id の配列。件数に上限あり)
        - 動作: 現在値より新しいときだけ `last_seen_at` を `crawl_started_at` にする。
          他のフィールドは変えず、文書がなくても作らない
        - 応答: 200 `{"results": [{"document_id", "result"}]}`。`result` は
          updated/unchanged/not_found/update_conflict/lock_not_owned
        - 冪等。エラー: 400(上限超過を含む)、409(受理条件。バッチ登録と同じ)、503
        """
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
        """ソース削除 1(api 4.6)。終了していない削除結果を破棄する。

        POST /sources/{source_id}/deletions:discard(呼び出し元: Crawler のソース削除ジョブ)
        - リクエスト: `lock`(形式のみ検証し、所有は確認しない)、任意で `reason`
          (`source_deleted` のみ)
        - 動作: そのソースの終端状態でない削除結果を `discarded`(`source_deleted`)にする。
          実行中の削除バッチより優先し、応答の時点でそのソースの削除バッチは動いていない
        - 応答: 200 `{"discarded_crawl_ids": [...]}`
        - 冪等。エラー: 400、503(試行の上限を超えても終端でない結果が残った場合)
        """
        body = parse_model(DiscardBody, raw_body)
        discarded = dependencies.deletion.discard_source_crawls(source_id, body.lock.to_domain())
        return {"discarded_crawl_ids": discarded}

    @router.delete("/sources/{source_id}/documents", response_model=None)
    def delete_source_documents(source_id: SourceId, raw_body: RawBody) -> dict[str, object]:
        """ソース削除 2(api 4.7)。検索インデックスからそのソースの文書をすべて削除する。

        DELETE /sources/{source_id}/documents(呼び出し元: Crawler。ソース削除 1 の後)
        - リクエスト: ボディ `{"lock": {"owner", "job_id"}}`(必須。ロックの所有を確認する)
        - 動作: `delete_by_query` を再実行して消し切る
        - 応答: 200 `{"deleted_count": n}`
        - 冪等(再送では 0 件でも成功)。
          エラー: 400、409 `lock_not_owned`(何も書かない)、503(再実行の上限超過)
        """
        body = parse_model(LockedBody, raw_body)
        deleted_count = dependencies.deletion.delete_source_documents(
            source_id, body.lock.to_domain()
        )
        return {"deleted_count": deleted_count}

    @router.delete("/sources/{source_id}/deletion-records", response_model=None)
    def delete_source_records(source_id: SourceId, raw_body: RawBody) -> dict[str, object]:
        """ソース削除 3(api 4.8)。そのソースの削除記録を削除する。

        DELETE /sources/{source_id}/deletion-records(呼び出し元: Crawler。ソース削除 2 の後)
        - リクエスト: ボディ `{"lock": {"owner", "job_id"}}`(必須。ロックの所有を確認する)
        - 動作: `loreley-deletions` の `deletion-{source_id}` と `deletion_result-*` を削除する
        - 応答: 200 `{"deleted": true}`(すでに記録がなければ false。成功扱い)
        - 冪等。エラー: 400、409 `lock_not_owned`(何も書かない)
        """
        body = parse_model(LockedBody, raw_body)
        deleted = dependencies.deletion.delete_source_records(source_id, body.lock.to_domain())
        return {"deleted": deleted}

    return router
