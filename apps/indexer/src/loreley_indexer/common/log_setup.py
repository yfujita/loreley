"""ログ出力の初期設定(R9: ログに本文と秘密情報を出さない)。

`main.py` が起動時に 1 回呼ぶ。次の 3 点を行う。
- ハンドラに `SecretRedactionFilter` を付け、設定から分かっている秘密値を伏せる。
- 本文・ID・応答が出るライブラリのロガーを ERROR 以上に固定する(ルートを DEBUG にしても出ない)。
  opensearch-py は、失敗した呼び出し(404 などの通常の応答を含む)ごとに、ID を含む URL を
  WARNING で、成功にも INFO で出し、DEBUG では本文・応答を、トレース用のロガーでは本文つきの
  curl コマンドを出す。失敗は例外としてアプリ側が種別名だけをログに出すので、ERROR 以上に
  固定しても情報は失われない。urllib3 も DEBUG で ID を含むリクエストのパスを出す。
- ルートロガーのハンドラを置き換える(二重に出力しない)。

ロガー名は、ライブラリが実際に使う名前を文字列で持つ(`opensearch` と `opensearchpy.trace` の
ように、パッケージ名と異なる名前を使う。食い違うと制限が効かず黙って漏れる)。外部ライブラリは
`infrastructure` だけが import できる(R2)ので、`common` はライブラリを import せず、
一致はテストが、インストール済みのライブラリから確かめる(`tests/common/test_log_setup.py`)。
"""

import logging
from collections.abc import Iterable
from typing import TextIO

from loreley_indexer.common.log_masking import SecretRedactionFilter

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

# ライブラリが実際に使うロガー。子のロガー(`opensearchpy.*`)もまとめて制限するため、
# パッケージ名のロガーも含める。
RESTRICTED_LOGGER_NAMES = (
    "opensearch",  # 失敗・成功のログ、DEBUG の本文・応答
    "opensearchpy",  # 子(`opensearchpy.trace`・`opensearchpy.helpers` など)をまとめて
    "opensearchpy.trace",  # 本文つきの curl コマンド
    "opensearchpy.helpers",
    "urllib3",
)
RESTRICTED_LOG_LEVEL = logging.ERROR


def configure_logging(
    *, level: int | str, secrets: Iterable[str], stream: TextIO | None = None
) -> logging.Handler:
    """ログの出力先(`stream`。省略時は stderr)と水準を設定し、付けたハンドラを返す。"""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(SecretRedactionFilter(secrets))

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in RESTRICTED_LOGGER_NAMES:
        logging.getLogger(name).setLevel(RESTRICTED_LOG_LEVEL)
    return handler
