"""秘密値(パスワードなど)・入力値がどこにも出ていないことの共通のアサーション。

後続フェーズのルーターのテストでも、応答とログに対して同じ検査を使い回す(`log_records.py` と同様)。
"""

import logging
from collections.abc import Sequence

from tests.log_records import server_side_text


def assert_secret_absent(
    secret: str,
    *,
    response_text: str = "",
    records: Sequence[logging.LogRecord] = (),
    captured_text: str = "",
) -> None:
    """`secret` が、HTTP 応答・サーバー側のログ記録(引数・`extra`・例外を含む)・出力に含まれない。

    テストのクライアント(httpx)が出すログは、サーバー側の実装のログではないので対象外。
    """
    assert secret not in response_text, "the secret is in the HTTP response"
    assert secret not in server_side_text(list(records)), "the secret is in the log records"
    assert secret not in captured_text, "the secret is in the captured output"
