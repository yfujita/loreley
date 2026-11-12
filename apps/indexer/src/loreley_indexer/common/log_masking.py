"""ログのマスキング(R9: ログに本文と秘密情報を出さない)。

本文は値からは判別できないため、そもそもログに渡さないことを原則とする。
ここで扱うのは、設定から値が分かっている秘密情報(パスワードなど)と、
URL に埋め込まれた認証情報。

伏せる対象は、メッセージ(引数の整形後)と例外の traceback のみ。
`stack_info` と `extra`(ログ記録に付く独自の属性)は伏せない。
`extra` に秘密値を渡さないこと。
"""

import logging
from collections.abc import Iterable
from urllib.parse import SplitResult, urlsplit, urlunsplit

REDACTED = "***"
UNFORMATTABLE_MESSAGE = "<log message could not be formatted>"


def redact_url_credentials(url: str) -> str:
    """`scheme://user:pass@host:port/...` のユーザー情報を伏せる。"""
    parts = urlsplit(url)
    if parts.username is None and parts.password is None:
        return url
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    port = _port_or_none(parts)
    port_suffix = f":{port}" if port is not None else ""
    return urlunsplit(parts._replace(netloc=f"{REDACTED}@{host}{port_suffix}"))


def _port_or_none(parts: SplitResult) -> int | None:
    """不正なポート(数字以外、範囲外)は、ログ用の表示から落とす。例外にはしない。"""
    try:
        return parts.port
    except ValueError:
        return None


class SecretRedactionFilter(logging.Filter):
    """既知の秘密値をログ本文・例外の文字列から伏せる。

    ロガーではなくハンドラに付けること(ロガーのフィルタは伝播してきた記録には効かない)。
    """

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        # 長い値から置換し、短い秘密が長い秘密の一部に当たって断片が残るのを防ぐ。
        # 空文字は全文字の間に挿入されてしまうので除く。
        self._secrets = sorted({s for s in secrets if s}, key=len, reverse=True)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(self._format_message(record))
        record.args = None
        if record.exc_info:
            formatted = logging.Formatter().formatException(record.exc_info)
            record.exc_text = self._redact(formatted)
            record.exc_info = None
        return True

    @staticmethod
    def _format_message(record: logging.LogRecord) -> str:
        """整形に失敗しても例外を伝播しない(ログ出力で処理を止めない)。

        原文は秘密値を含みうるため、失敗時はロガー名と例外クラス名だけの文言に置き換える。
        """
        try:
            return record.getMessage()
        except Exception as error:
            # 例外の文字列表現や args には秘密値が入りうるため、クラス名だけを残す。
            return f"{UNFORMATTABLE_MESSAGE} (logger={record.name}, error={type(error).__name__})"

    def _redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text
