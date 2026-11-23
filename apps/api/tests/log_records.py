"""ログ記録の検査に使う共通の関数。"""

import logging


def record_text(record: logging.LogRecord) -> str:
    """ログ記録が持つ、文字列になりうるすべて(メッセージ・引数・`extra`・例外・スタック)。"""
    return repr({**vars(record), "formatted": record.getMessage()})


# テストのクライアントが出すログ(リクエストの URL を出す)。サーバー側の実装のログではない。
TEST_CLIENT_LOGGERS = {"httpx", "httpx2", "httpcore", "httpcore2"}


def server_side_records(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    """テストのクライアント以外のすべてのロガー(`loreley_api`・uvicorn・asyncio など)の記録。"""
    return [record for record in records if record.name.split(".")[0] not in TEST_CLIENT_LOGGERS]


def server_side_text(records: list[logging.LogRecord]) -> str:
    return "".join(record_text(record) for record in server_side_records(records))
