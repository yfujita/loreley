"""`indexer_client` の設定。値は仮値で、設定可能(`config.py` が詰める。architecture 11章)。"""

from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ApiTimeouts:
    """API ごとの応答待ちのタイムアウト(秒)。既定値は architecture 11章の仮値。

    ソース削除 1(discard)は実行中の削除バッチの完了を待つので長く、ソース削除 2 は
    `delete_by_query` を再実行して消し切るので、さらに長い(Indexer の設定に依存する。
    Indexer の再実行回数を上げたら、合わせて延ばす)。待ちの間もハートビートは続く(別スレッド)。
    """

    start: float = 30.0
    finish: float = 30.0
    status: float = 30.0
    last_seen: float = 60.0
    register_batch: float = 300.0
    discard_deletions: float = 600.0
    delete_documents: float = 4_200.0
    delete_deletion_records: float = 60.0

    def __post_init__(self) -> None:
        for name, seconds in vars(self).items():
            if seconds <= 0:
                raise ValueError(f"the timeout of {name} must be positive")


@dataclass(frozen=True)
class IndexerClientConfig:
    """`base_url` は `http://indexer:8000` のような接続先(パスを含めない)。

    `connect_timeout_seconds` は接続の確立のタイムアウトで、API に共通(仮値。architecture 11章に
    値はない)。接続できない Indexer(起動前など)で、リトライの待ちを長引かせないために短くする。
    """

    base_url: str
    timeouts: ApiTimeouts = field(default_factory=ApiTimeouts)
    connect_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        # URL を解釈できない場合、標準ライブラリの `ValueError` は URL の一部をメッセージに入れる。
        # 固定文に置き換える(`except` の外で送出し、元の例外を `__context__` に残さない)。
        try:
            parts = urlsplit(self.base_url)
            _port = parts.port
        except ValueError:
            is_parsable = False
        else:
            is_parsable = True
        if not is_parsable:
            raise ValueError("the Indexer URL is invalid")
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("the Indexer URL must be an http(s) URL with a host")
        if parts.username is not None or parts.password is not None:
            raise ValueError("credentials must not be embedded in the Indexer URL")
        if parts.path not in {"", "/"} or parts.query or parts.fragment:
            raise ValueError("the Indexer URL must not include a path, query or fragment")
        if self.connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds must be positive")
