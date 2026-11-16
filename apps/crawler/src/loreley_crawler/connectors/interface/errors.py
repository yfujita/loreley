"""Connector のエラー分類と属性(interface 6章)。

分類名・`scope`・`retry` は interface 6.2 の表のとおり。各分類の `scope` と `retry` は発生点ごとに
1 つに定まるので、`ConnectorError.of` が表から補う(例外は `connector_internal_error` の `scope`。
列挙・`create`・`validate_config` は source、取得は document で、呼び出し側が決める)。

`message` には、原因の特定に足る情報(errno 名、切り詰めた相対パスなど)を入れてよいが、文書の本文・
認証情報は入れない(interface 6.1。CI-P-17)。呼び出し側は、外部由来の文字列を `common` の
`format_display_text` に通してから入れること。
"""

import errno
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum


class ErrorCategory(StrEnum):
    CONFIG_INVALID = "config_invalid"
    SOURCE_UNREACHABLE = "source_unreachable"
    SOURCE_NOT_FOUND = "source_not_found"
    SOURCE_ACCESS_DENIED = "source_access_denied"
    ENUMERATION_INCOMPLETE = "enumeration_incomplete"
    FETCH_NOT_FOUND = "fetch_not_found"
    FETCH_PERMISSION_DENIED = "fetch_permission_denied"
    FETCH_TRANSIENT = "fetch_transient"
    OVERSIZE = "oversize"
    INVALID_EXTERNAL_ID = "invalid_external_id"
    EXTERNAL_ID_COLLISION = "external_id_collision"
    CONNECTOR_INTERNAL_ERROR = "connector_internal_error"


class ErrorScope(StrEnum):
    SOURCE = "source"
    DOCUMENT = "document"


class RetryHint(StrEnum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    UNKNOWN = "unknown"


# interface 6.2。`connector_internal_error` の `scope` は発生点で変わるため、ここには載せない。
_ATTRIBUTES: dict[ErrorCategory, tuple[ErrorScope, RetryHint]] = {
    ErrorCategory.CONFIG_INVALID: (ErrorScope.SOURCE, RetryHint.PERMANENT),
    ErrorCategory.SOURCE_UNREACHABLE: (ErrorScope.SOURCE, RetryHint.TRANSIENT),
    ErrorCategory.SOURCE_NOT_FOUND: (ErrorScope.SOURCE, RetryHint.PERMANENT),
    ErrorCategory.SOURCE_ACCESS_DENIED: (ErrorScope.SOURCE, RetryHint.PERMANENT),
    ErrorCategory.ENUMERATION_INCOMPLETE: (ErrorScope.SOURCE, RetryHint.UNKNOWN),
    ErrorCategory.FETCH_NOT_FOUND: (ErrorScope.DOCUMENT, RetryHint.PERMANENT),
    ErrorCategory.FETCH_PERMISSION_DENIED: (ErrorScope.DOCUMENT, RetryHint.PERMANENT),
    ErrorCategory.FETCH_TRANSIENT: (ErrorScope.DOCUMENT, RetryHint.TRANSIENT),
    ErrorCategory.OVERSIZE: (ErrorScope.DOCUMENT, RetryHint.PERMANENT),
    ErrorCategory.INVALID_EXTERNAL_ID: (ErrorScope.DOCUMENT, RetryHint.PERMANENT),
    ErrorCategory.EXTERNAL_ID_COLLISION: (ErrorScope.DOCUMENT, RetryHint.PERMANENT),
}


class ConnectorError(Exception):
    """Connector(と、識別子由来のものは共通処理)が送出する、分類つきの失敗。

    列挙の `next()` が送出したものを、列挙の `Failed` と呼ぶ(interface 3.2)。
    """

    def __init__(
        self, category: ErrorCategory, scope: ErrorScope, retry: RetryHint, message: str
    ) -> None:
        # `copy`・`pickle` が 4 つの引数で復元できるよう、`args` に全部を渡す。
        super().__init__(category, scope, retry, message)
        self.category = category
        self.scope = scope
        self.retry = retry
        self.message = message

    @classmethod
    def of(
        cls, category: ErrorCategory, message: str, *, scope: ErrorScope | None = None
    ) -> "ConnectorError":
        """interface 6.2 の表の `scope`・`retry` で作る。`scope` を渡すのは内部エラーだけ。"""
        if category is ErrorCategory.CONNECTOR_INTERNAL_ERROR:
            if scope is None:
                raise ValueError("scope is required for connector_internal_error")
            return cls(category, scope, RetryHint.UNKNOWN, message)
        if scope is not None:
            raise ValueError("scope is fixed by the category")
        fixed_scope, retry = _ATTRIBUTES[category]
        return cls(category, fixed_scope, retry, message)

    def __str__(self) -> str:
        return self.message


def errno_name(error: OSError) -> str:
    """`ENOENT` のような errno 名。errno を持たない・未知の値は `UNKNOWN`。"""
    if error.errno is None:
        return "UNKNOWN"
    return errno.errorcode.get(error.errno, "UNKNOWN")


def to_connector_error(error: Exception, scope: ErrorScope) -> ConnectorError:
    """想定外の例外を `connector_internal_error` にする(interface 3.2。CI-P-12)。

    説明文には例外の型名(と、`OSError` なら errno 名)だけを入れる。例外のメッセージには
    パスや設定の値が入りうるので、そのままは使わない。
    """
    detail = type(error).__name__
    if isinstance(error, OSError):
        detail = f"{detail} {errno_name(error)}"
    return ConnectorError.of(
        ErrorCategory.CONNECTOR_INTERNAL_ERROR, f"想定外の例外: {detail}", scope=scope
    )


@contextmanager
def converting_unexpected_errors(scope: ErrorScope) -> Iterator[None]:
    """ブロック内の `ConnectorError` 以外の例外を `connector_internal_error` に変換する。

    `Exception` だけを対象にする(`KeyboardInterrupt` などは変換しない)。元の例外は連鎖に残さない
    (`from None`)。例外のメッセージ(`OSError` のファイル名、値の repr など)が、
    `logger.exception` を通じて生のパス・設定値としてログに出るのを防ぐ(R11)。必要な情報
    (型名・errno 名)は説明文に入れてある。
    """
    try:
        yield
    except ConnectorError:
        raise
    except Exception as error:
        raise to_connector_error(error, scope) from None
