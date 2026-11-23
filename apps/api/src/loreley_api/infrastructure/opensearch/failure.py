"""読み取りの失敗の分類(C 3.2・5.8。D 4.8)。

OpenSearch の例外と、HTTP 200 のまま返る部分的な失敗・形の異常を、`Failed`(種別 `timeout` /
`unavailable`、対象 `store` / `search_index`)にする。**タイムアウトを優先する**(遅いのか止まって
いるのかを区別する)。

ログに出すのは、固定の操作名・分類・例外のクラス名・整数のステータス・(400 だけ)`error.type` に
限る。`str(例外)` は `root_cause` の理由・リソース ID を含みうるので出さない(A 5.5。R11)。
`urllib3.exceptions` を import してよいのは、このファイルと `health_probe.py` だけ(R5)。
"""

import logging
import re
from collections.abc import Callable, Mapping

from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError
from opensearchpy.exceptions import ConnectionTimeout, RequestError, TransportError
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError

from loreley_api.common.results import Failed, FailureTarget, Ok, Result

logger = logging.getLogger(__name__)

# `error.type` は OpenSearch の識別子(`parsing_exception` など)。想定外の形は出さない。
_SAFE_ERROR_TYPE = re.compile(r"[a-z_]{1,64}")
_UNKNOWN = "unknown"


class PartialResponseError(Exception):
    """HTTP 200 の応答の一部が失敗している(`timed_out=true`・`_shards.failed>0`)。"""

    def __init__(self, *, timed_out: bool) -> None:
        super().__init__("partial response")
        self.timed_out = timed_out


class ResponseShapeError(Exception):
    """応答が期待の形でない(必須の項目がない・型が違う)。"""


class ResultLimitExceededError(Exception):
    """結果が取りこぼしなく取れる上限を超えた(`loreley-sources` の 10,000 件など)。"""


class DocumentError(Exception):
    """`mget` の `docs[i].error`、または `found` が真偽値でない文書。理由文は持たない。"""


class SubRequestError(Exception):
    """`msearch` の `responses[i].error`。理由文は持たない。"""


def is_timeout(error: BaseException) -> bool:
    """接続・読み取りのタイムアウトか(C 5.8)。

    opensearch-py は、urllib3 の読み取りのタイムアウトだけを `ConnectionTimeout` にし、接続の
    タイムアウトは `ConnectionError`(`info` が元の例外)にする。`NewConnectionError`(接続拒否・
    名前解決の失敗)は `ConnectTimeoutError` の子だが、タイムアウトではない。
    """
    if isinstance(error, ConnectionTimeout):
        return True
    if isinstance(error, PartialResponseError):
        return error.timed_out
    if isinstance(error, OpenSearchConnectionError):
        info = error.info
        return isinstance(info, ConnectTimeoutError) and not isinstance(info, NewConnectionError)
    return False


def failed_from_exception(error: Exception, target: FailureTarget, *, operation: str) -> Failed:
    """例外(部分的な失敗の印を含む)を `Failed` にして、固定の項目だけをログに残す。

    `operation` は呼び出し側が決める固定の識別子(`jobs.list_jobs` など。ID を含めない)。
    """
    failed = Failed(
        kind="timeout" if is_timeout(error) else "unavailable",
        target=target,
        error_class_name=type(error).__name__,
    )
    if isinstance(error, RequestError):
        # 400 は、実装・スキーマの不一致を示すことが多い。応答の扱いは他の失敗と同じ。
        logger.error(
            "opensearch rejected a request: operation=%s status=400 error_type=%s",
            operation,
            _error_type_of(error),
        )
    else:
        logger.warning(
            "opensearch read failed: operation=%s target=%s kind=%s error=%s status=%s",
            operation,
            target,
            failed.kind,
            failed.error_class_name,
            _status_of(error),
        )
    return failed


def guarded_read[T](operation: str, target: FailureTarget, read: Callable[[], T]) -> Result[T]:
    """`read()` の例外を漏らさず、`Ok` か `Failed` にする。

    `BaseException`(`KeyboardInterrupt` など)は捕捉しない。
    """
    try:
        return Ok(read())
    except Exception as error:
        return failed_from_exception(error, target, operation=operation)


def _status_of(error: Exception) -> str:
    if isinstance(error, TransportError) and isinstance(error.status_code, int):
        return str(error.status_code)
    return "n/a"


def _error_type_of(error: TransportError) -> str:
    info = error.info
    if not isinstance(info, Mapping):
        return _UNKNOWN
    detail = info.get("error")
    if not isinstance(detail, Mapping):
        return _UNKNOWN
    error_type = detail.get("type")
    if isinstance(error_type, str) and _SAFE_ERROR_TYPE.fullmatch(error_type):
        return error_type
    return _UNKNOWN
