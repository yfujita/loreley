"""ログ出力の初期設定。

`main.py` が起動時に 1 回呼ぶ。ルートロガーのハンドラを置き換え(二重に出力しない)、
uvicorn のアクセスログ(ID を含む実際のパスを出す)を ERROR 以上に固定する。uvicorn は
`access_log=False` で起動するが、設定ミスでログが出てもルートを DEBUG にして漏れないように、
二重に防ぐ。

OpenSearch などのライブラリのロガーの制限は、そのライブラリを導入する実装(infrastructure)で足す。
"""

import logging
from typing import TextIO

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

RESTRICTED_LOGGER_NAMES = ("uvicorn.access",)
RESTRICTED_LOG_LEVEL = logging.ERROR


def configure_logging(*, level: int | str, stream: TextIO | None = None) -> logging.Handler:
    """ログの出力先(`stream`。省略時は stderr)と水準を設定し、付けたハンドラを返す。"""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in RESTRICTED_LOGGER_NAMES:
        logging.getLogger(name).setLevel(RESTRICTED_LOG_LEVEL)
    return handler
