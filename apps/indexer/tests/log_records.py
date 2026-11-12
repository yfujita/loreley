"""ログ記録の検査に使う共通の関数。"""

import logging


def record_text(record: logging.LogRecord) -> str:
    """ログ記録が持つ、文字列になりうるすべて(メッセージ・引数・`extra`・例外・スタック)。"""
    return repr({**vars(record), "formatted": record.getMessage()})
