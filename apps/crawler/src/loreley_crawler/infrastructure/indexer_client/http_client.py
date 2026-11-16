"""`IndexerClient` の HTTP 実装(urllib3。module 4.9)。

HTTP クライアントに urllib3 を選んだ理由(CM-U-2。選定は実装時):
- `DELETE` に JSON ボディを載せられる(`PoolManager.request` が、メソッドにかかわらず `body` を
  そのまま送る)。ソース削除 2・3 が `lock` をボディで運ぶため(CM-K-5)。ローカルの HTTP
  サーバに対する契約テストで、ボディが落ちないことを確認している(architecture 12章 #17)。
- API ごとのタイムアウトを、リクエストごとに `Timeout` で渡せる。
- コネクションプールがスレッドセーフで、同期呼び出しに向く(Job Runner のスレッドが使う)。
- opensearch-py がすでに依存しているので、新しい依存が増えない(直接 import するため、
  `pyproject.toml` に明記した)。

タイムアウトの意味: `Timeout(read=…)` は、**1 回の受信ごとの待ち**(応答が全く来ない最大の
待ち)で、応答全体の所要時間の上限ではない。Indexer は応答を 1 回で返すので、実質は
「応答までの待ち」。応答が少しずつ届き続けると、合計はこれを超えうる(想定しない)。
`connect` は接続の確立の待ち。

リトライ・リダイレクトはしない(`retries=False`・`redirect=False`)。接続の異常は、呼び出し側が
リトライする(`IndexerUnavailable`)。リトライが二重になると、確認点(所有・取り消し)を通せない。

ログには何も出さない(R11: 本文・秘密・Indexer への要請の本文を出さない)。結果にも、リクエストの
値と Indexer のエラーメッセージを載せない。urllib3 のロガーは `common/log_setup` が ERROR 以上に
固定する(DEBUG ではパスの ID が出るため)。
"""

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

import urllib3
from urllib3.exceptions import HTTPError, NewConnectionError
from urllib3.exceptions import TimeoutError as Urllib3TimeoutError

from loreley_crawler.infrastructure.indexer_client import parsing, payloads
from loreley_crawler.infrastructure.indexer_client.client import IndexerClient
from loreley_crawler.infrastructure.indexer_client.config import IndexerClientConfig
from loreley_crawler.infrastructure.indexer_client.models import (
    DocumentToRegister,
    FinishOutcome,
    LockInfo,
)
from loreley_crawler.infrastructure.indexer_client.parsing import MalformedResponseError
from loreley_crawler.infrastructure.indexer_client.results import (
    MALFORMED_RESPONSE,
    BatchReply,
    DeleteDocumentsReply,
    DeleteRecordsReply,
    DiscardReply,
    FinishReply,
    IndexerRejected,
    IndexerUnavailable,
    LastSeenReply,
    StartReply,
    StatusReply,
    Succeeded,
)


def _succeeded(data: bytes) -> Succeeded:
    """開始通知・終了通知は、応答の本文を使わない(空でもよい)。"""
    return Succeeded()


# 再試行の対象にする HTTP ステータス(architecture 7.8)。それ以外のエラーは `IndexerRejected`。
UNAVAILABLE_STATUS_CODES = frozenset({500, 503})
JSON_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


class HttpIndexerClient(IndexerClient):
    def __init__(self, config: IndexerClientConfig, *, pool: urllib3.PoolManager | None = None):
        self._base_url = config.base_url.rstrip("/")
        self._timeouts = config.timeouts
        self._connect_timeout_seconds = config.connect_timeout_seconds
        # 呼ぶスレッドは Job Runner の 1 つだけ(R9)。接続はこのクライアントだけが持つ。
        self._pool = pool if pool is not None else urllib3.PoolManager(num_pools=1)

    def close(self) -> None:
        self._pool.clear()

    def start_crawl(
        self,
        *,
        crawl_id: str,
        source_id: str,
        crawl_started_at: datetime,
        ttl: int,
        ratio_threshold: float,
        min_delete_count: int,
        force_delete: bool,
        rewrite_mode: bool,
    ) -> StartReply:
        payload = payloads.start_payload(
            crawl_id=crawl_id,
            source_id=source_id,
            crawl_started_at=crawl_started_at,
            ttl=ttl,
            ratio_threshold=ratio_threshold,
            min_delete_count=min_delete_count,
            force_delete=force_delete,
            rewrite_mode=rewrite_mode,
        )
        return self._call(
            "POST",
            payloads.start_path(),
            payload,
            self._timeouts.start,
            _succeeded,
            expected_status=200,
        )

    def report_last_seen(
        self,
        source_id: str,
        *,
        crawl_id: str,
        crawl_started_at: datetime,
        lock: LockInfo,
        document_ids: Sequence[str],
    ) -> LastSeenReply:
        payload = payloads.last_seen_payload(
            crawl_id=crawl_id,
            crawl_started_at=crawl_started_at,
            lock=lock,
            document_ids=document_ids,
        )
        return self._call(
            "POST",
            payloads.last_seen_path(source_id),
            payload,
            self._timeouts.last_seen,
            lambda data: parsing.parse_last_seen(data, document_ids),
        )

    def register_documents(
        self,
        source_id: str,
        *,
        crawl_id: str,
        crawl_started_at: datetime,
        lock: LockInfo,
        documents: Sequence[DocumentToRegister],
    ) -> BatchReply:
        payload = payloads.batch_payload(
            crawl_id=crawl_id, crawl_started_at=crawl_started_at, lock=lock, documents=documents
        )
        return self._call(
            "POST",
            payloads.batch_path(source_id),
            payload,
            self._timeouts.register_batch,
            lambda data: parsing.parse_batch(
                data, [document.external_id for document in documents]
            ),
        )

    def finish_crawl(
        self,
        crawl_id: str,
        *,
        source_id: str,
        outcome: FinishOutcome,
        finished_at: datetime,
        enumerated_count: int | None = None,
        skipped_document_ids: Sequence[str] | None = None,
        oversize_document_ids: Sequence[str] | None = None,
    ) -> FinishReply:
        payload = payloads.finish_payload(
            source_id=source_id,
            outcome=outcome,
            finished_at=finished_at,
            enumerated_count=enumerated_count,
            skipped_document_ids=skipped_document_ids,
            oversize_document_ids=oversize_document_ids,
        )
        return self._call(
            "POST",
            payloads.finish_path(crawl_id),
            payload,
            self._timeouts.finish,
            _succeeded,
            expected_status=202,
        )

    def get_crawl_status(self, crawl_id: str) -> StatusReply:
        return self._call(
            "GET",
            payloads.status_path(crawl_id),
            None,
            self._timeouts.status,
            parsing.parse_status,
        )

    def discard_deletions(self, source_id: str, *, lock: LockInfo) -> DiscardReply:
        return self._call(
            "POST",
            payloads.discard_path(source_id),
            payloads.discard_payload(lock),
            self._timeouts.discard_deletions,
            parsing.parse_discard,
        )

    def delete_documents(self, source_id: str, *, lock: LockInfo) -> DeleteDocumentsReply:
        return self._call(
            "DELETE",
            payloads.delete_documents_path(source_id),
            payloads.locked_payload(lock),
            self._timeouts.delete_documents,
            parsing.parse_documents_deleted,
        )

    def delete_deletion_records(self, source_id: str, *, lock: LockInfo) -> DeleteRecordsReply:
        return self._call(
            "DELETE",
            payloads.delete_deletion_records_path(source_id),
            payloads.locked_payload(lock),
            self._timeouts.delete_deletion_records,
            parsing.parse_deletion_records_deleted,
        )

    def _call[ReplyT](
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        timeout_seconds: float,
        parse: Callable[[bytes], ReplyT],
        *,
        expected_status: int = 200,
    ) -> ReplyT | IndexerUnavailable | IndexerRejected:
        body = payloads.encode_json(payload) if payload is not None else None
        try:
            response = self._pool.request(
                method,
                f"{self._base_url}{path}",
                body=body,
                headers=JSON_HEADERS if body is not None else {"Accept": "application/json"},
                timeout=urllib3.Timeout(
                    connect=self._connect_timeout_seconds, read=timeout_seconds
                ),
                retries=False,
                redirect=False,
            )
        except NewConnectionError:
            # 接続できない(起動前の接続拒否を含む)。`ConnectTimeoutError` の子クラスなので、
            # タイムアウトより先に判定する。
            return IndexerUnavailable("connection_error")
        except Urllib3TimeoutError:
            return IndexerUnavailable("timeout")
        except HTTPError:
            return IndexerUnavailable("connection_error")
        return self._reply(response.status, response.data, parse, expected_status)

    @staticmethod
    def _reply[ReplyT](
        status: int, data: bytes, parse: Callable[[bytes], ReplyT], expected_status: int
    ) -> ReplyT | IndexerUnavailable | IndexerRejected:
        if 200 <= status < 300:
            # 契約の成功のステータス(開始通知などは 200、終了通知は 202)以外の 2xx は、契約外。
            if status != expected_status:
                return IndexerRejected(status, MALFORMED_RESPONSE)
            try:
                return parse(data)
            except MalformedResponseError:
                return IndexerRejected(status, MALFORMED_RESPONSE)
        if status in UNAVAILABLE_STATUS_CODES:
            return IndexerUnavailable(f"http_{status}")
        return IndexerRejected(status, parsing.parse_error_code(data))
