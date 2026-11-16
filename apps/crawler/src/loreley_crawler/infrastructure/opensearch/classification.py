"""opensearch-py の例外・応答から結果区分への分類(module 4.8。architecture 3.1・9章)。

- OpenSearch 全体の異常は `StoreUnavailableError` を送出する: 接続エラー・タイムアウト・
  401/403・429・5xx、`cluster_block_exception`・`circuit_breaking_exception`・
  `index_not_found_exception`(HTTP ステータスにかかわらず)。
- 409 は `Conflict`、記録がない 404 は `NotFound`。
- 全件走査の PIT が期限切れ・閉じられていて使えない(`search_context_missing_exception`。
  `search_phase_execution_exception` の `root_cause` に入って 404 で返る)ときは、
  `StoreUnavailableError("pit_expired")`。呼び出し側は、走査をやり直す(リトライ)。
- それ以外の 4xx と、HTTP 応答ではない opensearch-py の例外(`SerializationError` など。
  `TransportError` の子ではない)は想定外の応答(クエリやマッピングの誤り、応答を解釈できない
  など。Crawler の不具合の疑い)で、`StoreUnexpectedResponseError` を送出する。

例外の文字列表現(`str(error)`)・OpenSearch の `reason` には、記録の内容(認証情報の参照名を含む
設定など)が含まれうるため、使わない。送出する例外も元の例外と連鎖させない(`from None`。
トレースバックの出力に載るため)。理由は種別名だけにする。
"""

from typing import Any

from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError
from opensearchpy.exceptions import (
    ConnectionTimeout,
    OpenSearchException,
    SerializationError,
    TransportError,
)

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.infrastructure.opensearch.results import Conflict, NotFound

# HTTP ステータスにかかわらず、索引・クラスタ全体の異常とみなすエラー種別。
UNAVAILABLE_ERROR_TYPES = frozenset(
    {"cluster_block_exception", "circuit_breaking_exception", "index_not_found_exception"}
)
# 認証・認可の誤りは、記録ではなく接続設定・権限の問題で、どの記録でも起きる。全体の異常にする。
AUTH_ERROR_STATUS_CODES = frozenset({401, 403})
HTTP_TOO_MANY_REQUESTS = 429
MISSING_SEARCH_CONTEXT_ERROR_TYPE = "search_context_missing_exception"


def classify_failure(error: OpenSearchException) -> Conflict | NotFound:
    """`Conflict`・`NotFound` を返す。全体の異常・想定外の応答は例外を送出する。"""
    if not isinstance(error, TransportError):
        # 応答を解釈できない(`SerializationError`)など。HTTP のステータスを持たない。
        reason = (
            "serialization_error" if isinstance(error, SerializationError) else "opensearch_error"
        )
        raise StoreUnexpectedResponseError(reason) from None
    if isinstance(error, ConnectionTimeout):
        raise StoreUnavailableError("connection_timeout") from None
    if isinstance(error, OpenSearchConnectionError):
        raise StoreUnavailableError("connection_error") from None

    status_code = error.status_code
    if not isinstance(status_code, int):
        raise StoreUnavailableError("transport_error") from None

    error_type = extract_error_type(error.info, fallback=error.error)
    if error_type in UNAVAILABLE_ERROR_TYPES:
        raise StoreUnavailableError(error_type) from None
    if _is_missing_search_context(error.info, error_type):
        raise StoreUnavailableError("pit_expired") from None
    if (
        status_code in AUTH_ERROR_STATUS_CODES
        or status_code == HTTP_TOO_MANY_REQUESTS
        or status_code >= 500
    ):
        raise StoreUnavailableError(f"http_{status_code}") from None

    if status_code == 409:
        return Conflict()
    if status_code == 404 and _is_record_absent(error.info, error_type):
        return NotFound()
    raise StoreUnexpectedResponseError(error_type or f"http_{status_code}") from None


def extract_error_type(info: Any, *, fallback: Any = None) -> str | None:
    """応答本文(`info`)の `error.type`。なければ `fallback` が `*_exception` のときその値。"""
    if isinstance(info, dict):
        body_error = info.get("error")
        if isinstance(body_error, dict) and isinstance(body_error.get("type"), str):
            return body_error["type"]
    if isinstance(fallback, str) and fallback.endswith("_exception"):
        return fallback
    return None


def _is_missing_search_context(info: Any, error_type: str | None) -> bool:
    """PIT が期限切れ・閉じられている。本体の種別か、`root_cause` のどれかが該当する。"""
    if error_type == MISSING_SEARCH_CONTEXT_ERROR_TYPE:
        return True
    body_error = info.get("error") if isinstance(info, dict) else None
    root_causes = body_error.get("root_cause") if isinstance(body_error, dict) else None
    return isinstance(root_causes, list) and any(
        isinstance(cause, dict) and cause.get("type") == MISSING_SEARCH_CONTEXT_ERROR_TYPE
        for cause in root_causes
    )


def _is_record_absent(info: Any, error_type: str | None) -> bool:
    """GET・DELETE で存在しない記録は、`error` を持たない本文(`found: false` など)で返る。"""
    if error_type == "document_missing_exception":
        return True
    return isinstance(info, dict) and (
        info.get("found") is False or info.get("result") == "not_found"
    )
