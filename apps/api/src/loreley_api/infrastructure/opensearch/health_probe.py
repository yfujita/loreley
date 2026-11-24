"""`opensearch` の死活確認: `cluster.health` の応答の有無(C 6.2 の 2 つ目の表。D 4.8)。

プローブ用クライアント(短いタイムアウト・再試行なし。`create_probe_connection`)で 1 回だけ呼ぶ。
`red` でも応答できれば正常で、応答の形は見ない。OpenSearch の例外は `ConnectionError.info` の
`urllib3.exceptions` の型で分類する(`failure.py` と同じ理由。**このファイルと `failure.py` だけが
`urllib3.exceptions` を import してよい**。R5)。

ログには、固定の結果の区分と例外のクラス名だけを出す。URL・例外のメッセージは出さない(R11)。
"""

import logging
from typing import Protocol

from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError
from opensearchpy.exceptions import ConnectionTimeout, SSLError, TransportError
from urllib3.exceptions import ConnectTimeoutError, NameResolutionError, NewConnectionError

from loreley_api.common.probe_outcome import ProbeOutcome
from loreley_api.infrastructure.opensearch.readonly_client import ReadOnlyOpenSearch

logger = logging.getLogger(__name__)

_NORMAL = ProbeOutcome("normal")
_UNEXPECTED_STATUS = ProbeOutcome("abnormal", "unexpected_status")
_NAME_NOT_RESOLVED = ProbeOutcome("abnormal", "name_not_resolved")
_CONNECTION_REFUSED = ProbeOutcome("abnormal", "connection_refused")
_TIMEOUT = ProbeOutcome("undetermined", "timeout")
_CONNECTION_ERROR = ProbeOutcome("undetermined", "connection_error")


class OpenSearchHealthCheck(Protocol):
    """ブロッキング(`probe` の枠)。"""

    def check(self) -> ProbeOutcome: ...


class OpenSearchHealthProbe:
    def __init__(self, readonly: ReadOnlyOpenSearch) -> None:
        self._readonly = readonly

    def check(self) -> ProbeOutcome:
        outcome = self._check()
        logger.debug(
            "opensearch health probe finished: state=%s reason=%s",
            outcome.state,
            outcome.reason or "-",
        )
        return outcome

    def _check(self) -> ProbeOutcome:
        try:
            self._readonly.cluster_health()
        except Exception as error:
            # 確認は例外を漏らさない(想定外の例外も「判定不能」にする)。
            logger.debug("opensearch health probe failed: error=%s", type(error).__name__)
            return classify_health_error(error)
        return _NORMAL


def classify_health_error(error: Exception) -> ProbeOutcome:
    """例外を `state`・`reason` にする。狭いほうから順に判定する。

    `status_code` が整数なら HTTP エラーの応答(401・403・5xx など。応答が返った)で、`"N/A"` なら
    接続の失敗。`ConnectionTimeout`・`SSLError` は `ConnectionError` の子なので、先に判定する。
    """
    if isinstance(error, ConnectionTimeout):
        return _TIMEOUT
    if isinstance(error, SSLError):
        return _CONNECTION_ERROR
    if isinstance(error, OpenSearchConnectionError):
        return _classify_connection_failure(error.info)
    if isinstance(error, TransportError) and isinstance(error.status_code, int):
        return _UNEXPECTED_STATUS
    return _CONNECTION_ERROR


def _classify_connection_failure(cause: object) -> ProbeOutcome:
    """`ConnectionError.info`(元の urllib3 の例外)で、接続の失敗を分ける。"""
    if isinstance(cause, NameResolutionError):
        return _NAME_NOT_RESOLVED
    if isinstance(cause, NewConnectionError):
        return _CONNECTION_REFUSED
    if isinstance(cause, ConnectTimeoutError):
        return _TIMEOUT
    return _CONNECTION_ERROR
