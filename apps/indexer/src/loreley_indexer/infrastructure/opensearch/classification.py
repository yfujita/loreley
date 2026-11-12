"""opensearch-py の例外から結果区分への分類(arch 4.4、5章)。

OpenSearch 全体の異常は `OpenSearchUnavailableError` を送出する。
例外の文字列表現(`str(error)`)には文書の内容が含まれうるため、使わず、
送出する例外も元の例外と連鎖させない(`from None`。トレースバックの出力に載るため)。
"""

from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError
from opensearchpy.exceptions import ConnectionTimeout, TransportError

from loreley_indexer.infrastructure.opensearch.errors import OpenSearchUnavailableError
from loreley_indexer.infrastructure.opensearch.results import Conflict, NotFound, Rejected

# HTTP ステータスにかかわらず、索引・クラスタ全体の異常とみなすエラー種別。
UNAVAILABLE_ERROR_TYPES = frozenset(
    {"cluster_block_exception", "circuit_breaking_exception", "index_not_found_exception"}
)
# 認証・認可の誤り(`security_exception` など)は、文書ではなく接続設定・権限の問題で、
# どの文書でも起きる。文書固有の拒否として飛ばさず、全体異常にする(arch 4.4)。
AUTH_ERROR_STATUS_CODES = frozenset({401, 403})
DOCUMENT_MISSING_ERROR_TYPE = "document_missing_exception"


def classify_failure(error: TransportError) -> Conflict | NotFound | Rejected:
    if isinstance(error, ConnectionTimeout):
        raise OpenSearchUnavailableError("connection_timeout") from None
    if isinstance(error, OpenSearchConnectionError):
        raise OpenSearchUnavailableError("connection_error") from None

    status_code = error.status_code
    if not isinstance(status_code, int):
        raise OpenSearchUnavailableError("transport_error") from None

    error_type = _extract_error_type(error)
    if error_type in UNAVAILABLE_ERROR_TYPES:
        raise OpenSearchUnavailableError(error_type) from None
    if status_code in AUTH_ERROR_STATUS_CODES or status_code == 429 or status_code >= 500:
        raise OpenSearchUnavailableError(f"http_{status_code}") from None

    if status_code == 409:
        return Conflict()
    if status_code == 404 and _is_document_absent(error, error_type):
        return NotFound()
    return Rejected(error_type=error_type or f"http_{status_code}")


def _extract_error_type(error: TransportError) -> str | None:
    info = error.info
    if isinstance(info, dict):
        body_error = info.get("error")
        if isinstance(body_error, dict) and isinstance(body_error.get("type"), str):
            return body_error["type"]
    if isinstance(error.error, str) and error.error.endswith("_exception"):
        return error.error
    return None


def _is_document_absent(error: TransportError, error_type: str | None) -> bool:
    """GET・DELETE で存在しない文書は、`error` を持たない本文で返る(`found: false` など)。"""
    if error_type == DOCUMENT_MISSING_ERROR_TYPE:
        return True
    info = error.info
    return isinstance(info, dict) and (
        info.get("found") is False or info.get("result") == "not_found"
    )
