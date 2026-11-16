"""errno と分類名の対応、説明文(FS 設計書 3.3・4.4・7章。案: CFS-P-11・CFS-P-18)。

説明文は、固定文に errno 名と該当パスを足した形(例: 「ディレクトリを読み取れない: ESTALE,
`docs/a`」)。パスは長さを切り詰め、制御文字をエスケープする(R11。ログの行の偽造を防ぐ)。
ファイルの内容・認証情報は入れない。

表にない errno の `OSError` は分類せず、そのまま送出する(呼び出し側の `documents` が
`connector_internal_error` に変換する)。

分類した `ConnectorError` は元の `OSError` を連鎖に残さない(`from None`)。`OSError` はファイル名の
repr(制御文字を含みうる未加工のパス)を持ち、`logger.exception` で出るとログの行の偽造になる
(R11)。必要な情報(errno 名と、切り詰め・エスケープ済みのパス)は説明文にある。
"""

import errno
from collections.abc import Iterator
from contextlib import contextmanager

from loreley_crawler.common.display_text import format_display_text
from loreley_crawler.connectors.interface import ConnectorError, ErrorCategory, errno_name

# 集合 T: 到達不能・一時障害の errno(暫定。実機での確認後に見直す。CFS-U-4)。
UNREACHABLE_ERRNOS = frozenset(
    {
        errno.EIO,
        errno.ESTALE,
        errno.ETIMEDOUT,
        errno.ENOTCONN,
        errno.EHOSTDOWN,
        errno.EHOSTUNREACH,
        errno.ENETDOWN,
        errno.ENETUNREACH,
        errno.ECONNREFUSED,
        errno.ECONNRESET,
        errno.ECONNABORTED,
        errno.ENODEV,
        errno.EBUSY,
    }
)
ACCESS_DENIED_ERRNOS = frozenset({errno.EACCES, errno.EPERM})
# 起点のパスが存在しない・たどれない。
ROOT_NOT_FOUND_ERRNOS = frozenset({errno.ENOENT, errno.ENOTDIR, errno.ELOOP, errno.ENAMETOOLONG})
FETCH_NOT_FOUND_ERRNOS = frozenset({errno.ENOENT, errno.ENOTDIR, errno.EISDIR, errno.ELOOP})
# `follow_symlinks=true` のとき、これらはリンクが壊れている印で、列挙の失敗にしない(4.2)。
BROKEN_LINK_ERRNOS = frozenset({errno.ENOENT, errno.ELOOP, errno.ENOTDIR})


def describe_path(message: str, path: str, *, max_chars: int) -> str:
    """固定文にパスを足す。パスは切り詰めとエスケープを通す。"""
    return f"{message}: `{format_display_text(path, max_chars=max_chars)}`"


def _describe_os_error(message: str, error: OSError, path: str, *, max_chars: int) -> str:
    return describe_path(f"{message}: {errno_name(error)}", path, max_chars=max_chars)


def classify_root_error(error: OSError, root: str, *, max_chars: int) -> ConnectorError | None:
    """`create`・列挙の `root` の読み取りの失敗(7.1)。分類できなければ None。"""
    code = error.errno
    if code in ROOT_NOT_FOUND_ERRNOS:
        category, message = ErrorCategory.SOURCE_NOT_FOUND, "ルートが存在しない・たどれない"
    elif code in ACCESS_DENIED_ERRNOS:
        category, message = ErrorCategory.SOURCE_ACCESS_DENIED, "ルートを読み取る権限がない"
    elif code in UNREACHABLE_ERRNOS:
        category, message = ErrorCategory.SOURCE_UNREACHABLE, "ルートに到達できない"
    else:
        return None
    return ConnectorError.of(
        category, _describe_os_error(message, error, root, max_chars=max_chars)
    )


def classify_fetch_error(
    error: OSError, relative_path: str, *, max_chars: int
) -> ConnectorError | None:
    """`fetch` の読み取り中の失敗(7.1)。分類できなければ None(`EMFILE` など)。"""
    code = error.errno
    if code in FETCH_NOT_FOUND_ERRNOS:
        category, message = ErrorCategory.FETCH_NOT_FOUND, "文書が見つからない"
    elif code in ACCESS_DENIED_ERRNOS:
        category, message = ErrorCategory.FETCH_PERMISSION_DENIED, "文書を読み取る権限がない"
    elif code in UNREACHABLE_ERRNOS:
        category, message = ErrorCategory.FETCH_TRANSIENT, "文書を読み取れない(一時的な障害)"
    else:
        return None
    return ConnectorError.of(
        category, _describe_os_error(message, error, relative_path, max_chars=max_chars)
    )


def enumeration_incomplete(error: OSError, relative_path: str, *, max_chars: int) -> ConnectorError:
    """`root` 以外の読み取りの失敗。errno を問わず、完全な列挙を保証できない(4.4)。"""
    message = _describe_os_error(
        "ディレクトリを読み取れない", error, relative_path, max_chars=max_chars
    )
    return ConnectorError.of(ErrorCategory.ENUMERATION_INCOMPLETE, message)


@contextmanager
def translating_root_errors(root: str, *, max_chars: int) -> Iterator[None]:
    """ブロック内の `OSError` を、`root` の分類(7.1)の `ConnectorError` にする。"""
    try:
        yield
    except OSError as error:
        classified = classify_root_error(error, root, max_chars=max_chars)
        if classified is None:
            raise
        raise classified from None


@contextmanager
def translating_fetch_errors(relative_path: str, *, max_chars: int) -> Iterator[None]:
    """ブロック内の `OSError` を、`fetch` の分類(7.1)の `ConnectorError` にする。"""
    try:
        yield
    except OSError as error:
        classified = classify_fetch_error(error, relative_path, max_chars=max_chars)
        if classified is None:
            raise
        raise classified from None
