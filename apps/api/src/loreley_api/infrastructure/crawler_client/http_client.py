"""`CrawlerClient` の HTTP 実装(urllib3。C 4.1・4.2。D 4.9)。

送信の方針(C 4.1。冪等でない API を含むため、どれも「安全側(二重に実行しない)」に倒す):
- **1 回だけ送る**: `retries=False`(接続の確立の失敗も再送しない)。
- **リダイレクトに従わない**: `redirect=False`。3xx は契約外(502 の元)。
- **接続を使い回さない**: `Connection: close`。使い回した接続が相手に閉じられていたときの失敗は、
  「送る前」か「送った後」かが区別できず、起動系の結果判定があいまいになるため。管理操作の頻度は
  低く、内部ネットワークなので接続のコストは無視できる。
- タイムアウトは接続と応答(1 回の受信ごとの待ち。Crawler は応答を 1 回で返す)を別に持つ。

ログには、ルートのテンプレート・結果の区分・所要時間だけを DEBUG で出す。ID を含むパス・本文・
Crawler の `message` は出さない(R11)。urllib3 のロガーは `logging_setup` が ERROR 以上に固定する。
"""

import logging
import time

import urllib3
from urllib3.exceptions import HTTPError

from loreley_api.infrastructure.crawler_client import payloads, routes
from loreley_api.infrastructure.crawler_client.classification import classify_transport_failure
from loreley_api.infrastructure.crawler_client.client import (
    CrawlerContractViolation,
    CrawlerResult,
    CrawlerSourceSettings,
)
from loreley_api.infrastructure.crawler_client.config import CrawlerClientConfig
from loreley_api.infrastructure.crawler_client.parsing import (
    RESPONSE_MAX_BYTES,
    collect_within_limit,
    interpret_response,
)

logger = logging.getLogger(__name__)

# 成功のステータス(B 9.2)。これ以外の 2xx は契約外。
_REGISTER_STATUSES = frozenset({200, 201})
_OK_STATUS = frozenset({200})
_ACCEPTED_STATUS = frozenset({202})
_CANCEL_STATUSES = frozenset({200, 202})

# `crawler` の枠の上限(C 8.1)に合わせる。接続は使い回さないので、同時に開く接続の数の上限になる。
_POOL_MAXSIZE = 4
_READ_CHUNK_BYTES = 64 * 1024


class HttpCrawlerClient:
    def __init__(self, config: CrawlerClientConfig) -> None:
        self._base_url = config.base_url.rstrip("/")
        self._timeout = urllib3.Timeout(
            connect=config.connect_timeout_seconds, read=config.response_timeout_seconds
        )
        self._pool = urllib3.PoolManager(num_pools=1, maxsize=_POOL_MAXSIZE)

    def close(self) -> None:
        self._pool.clear()

    def register_source(
        self, source_id: str, connector_type: str, settings: CrawlerSourceSettings
    ) -> CrawlerResult:
        payload = payloads.register_payload(source_id, connector_type, settings)
        return self._exchange(routes.register_source(), payload, _REGISTER_STATUSES)

    def update_source(self, source_id: str, settings: CrawlerSourceSettings) -> CrawlerResult:
        payload = payloads.update_payload(settings)
        return self._exchange(routes.update_source(source_id), payload, _OK_STATUS)

    def start_delete_job(self, source_id: str) -> CrawlerResult:
        return self._exchange(routes.start_delete_job(source_id), None, _ACCEPTED_STATUS)

    def start_crawl(
        self, source_id: str, *, force_delete: bool, rewrite_mode: bool
    ) -> CrawlerResult:
        payload = payloads.crawl_payload(force_delete=force_delete, rewrite_mode=rewrite_mode)
        return self._exchange(routes.start_crawl(source_id), payload, _ACCEPTED_STATUS)

    def cancel_job(self, job_id: str) -> CrawlerResult:
        return self._exchange(routes.cancel_job(job_id), None, _CANCEL_STATUSES)

    def release_lock(self, source_id: str) -> CrawlerResult:
        return self._exchange(routes.release_lock(source_id), None, _OK_STATUS)

    def _exchange(
        self,
        route: routes.CrawlerRoute,
        payload: dict[str, object] | None,
        success_statuses: frozenset[int],
    ) -> CrawlerResult:
        started_at = time.monotonic()
        result = self._send_once(route, payload, success_statuses)
        logger.debug(
            "crawler call: route=%s %s outcome=%s elapsed_ms=%.1f",
            route.method,
            route.template,
            type(result).__name__,
            (time.monotonic() - started_at) * 1000,
        )
        return result

    def _send_once(
        self,
        route: routes.CrawlerRoute,
        payload: dict[str, object] | None,
        success_statuses: frozenset[int],
    ) -> CrawlerResult:
        body = payloads.encode_json(payload) if payload is not None else None
        headers = {"Accept": "application/json", "Connection": "close"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            # 本文は上限つきで自分で読むので、先読みしない(`preload_content=False`)。
            response = self._pool.request(
                route.method,
                f"{self._base_url}{route.path}",
                body=body,
                headers=headers,
                timeout=self._timeout,
                retries=False,
                redirect=False,
                preload_content=False,
            )
            try:
                data = collect_within_limit(response.stream(_READ_CHUNK_BYTES), RESPONSE_MAX_BYTES)
            finally:
                # 上限で読むのをやめたときは、未読の本文が残る接続を使い回させない。
                response.close()
                response.release_conn()
        except HTTPError as error:
            return classify_transport_failure(error)
        if data is None:
            return CrawlerContractViolation("body_too_large", response.status)
        return interpret_response(response.status, data, success_statuses=success_statuses)
