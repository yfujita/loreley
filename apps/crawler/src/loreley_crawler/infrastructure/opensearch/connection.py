"""OpenSearch への接続設定とクライアントの生成(module 4.8)。

クライアントは 2 種類を作る。
- Store 層のクライアント: Job Runner・HTTP ハンドラ・Scheduler のスレッドが共有する。
- ハートビート専用のクライアント: ロック文書のリース更新だけに使い、別の(短い)タイムアウトを
  持つ。再試行間隔とリース時間に収まる短さにする(module CM-P-14。Indexer の
  `delete_by_query` 専用クライアントに倣う)。

どちらも、トランスポート層の自動再送を無効にする(`max_retries=0`)。リトライは、確認点つきの
`common` の汎用機構を使って呼び出し側が行う(module CM-P-12)。自動再送があると、リトライが
二重になり、ハートビートのクライアントでは待ちが重なってリースの更新間隔に収まらなくなる。
複数スレッドから 1 つのクライアントを使えるか(CM-U-1)は実機で確認する。
"""

from contextlib import ExitStack
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from opensearchpy import OpenSearch

# 通常の読み書きの仮値。Indexer の `os_request_timeout_seconds` と同じ。
DEFAULT_STORE_REQUEST_TIMEOUT_SECONDS = 30.0
# ハートビート間隔(100 秒)より十分短い仮値(architecture 11章の「再試行間隔」の下に収める)。
DEFAULT_HEARTBEAT_REQUEST_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class OpenSearchConnectionConfig:
    url: str
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    verify_certs: bool = True
    ca_certs_path: str | None = None
    store_request_timeout_seconds: float = DEFAULT_STORE_REQUEST_TIMEOUT_SECONDS
    heartbeat_request_timeout_seconds: float = DEFAULT_HEARTBEAT_REQUEST_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        # URL を解釈できない場合、標準ライブラリの `ValueError` は URL の一部(認証情報を含む
        # netloc やポートの値)をメッセージに入れる。起動前の例外は標準エラー出力へそのまま出る
        # ため、固定文に置き換える。`except` の外で送出し、元の例外を `__context__` に残さない。
        try:
            parts = urlsplit(self.url)
            _port = parts.port  # 不正なポートは、アクセスしたときに `ValueError` になる
        except ValueError:
            is_parsable = False
        else:
            is_parsable = True
        if not is_parsable:
            raise ValueError("the OpenSearch URL is invalid")
        # URL に認証情報を埋め込むと、設定の表示やログから漏れやすい。専用の項目で渡させる。
        if parts.username is not None or parts.password is not None:
            raise ValueError("credentials must not be embedded in the OpenSearch URL")
        # 片方だけでは認証されない(黙って認証なしで接続しない)。
        if (self.username is None) != (self.password is None):
            raise ValueError("username and password must be set together")
        if self.store_request_timeout_seconds <= 0:
            raise ValueError("store_request_timeout_seconds must be positive")
        if self.heartbeat_request_timeout_seconds <= 0:
            raise ValueError("heartbeat_request_timeout_seconds must be positive")


def create_store_client(config: OpenSearchConnectionConfig) -> OpenSearch:
    return _create_client(config, request_timeout_seconds=config.store_request_timeout_seconds)


def create_heartbeat_client(config: OpenSearchConnectionConfig) -> OpenSearch:
    """ハートビート専用のクライアント。Store 層のクライアントとは接続を共有しない。"""
    return _create_client(config, request_timeout_seconds=config.heartbeat_request_timeout_seconds)


def close_clients(*clients: OpenSearch) -> None:
    """クライアントの接続プールを閉じる。1 つの `close()` が失敗しても、残りを閉じる。"""
    with ExitStack() as stack:
        for client in clients:
            stack.callback(client.close)


def _create_client(
    config: OpenSearchConnectionConfig,
    *,
    request_timeout_seconds: float,
) -> OpenSearch:
    http_auth = None
    if config.username is not None and config.password is not None:
        http_auth = (config.username, config.password)
    return OpenSearch(
        hosts=[config.url],
        http_auth=http_auth,
        verify_certs=config.verify_certs,
        ca_certs=config.ca_certs_path,
        timeout=request_timeout_seconds,
        max_retries=0,
        retry_on_timeout=False,
        retry_on_status=(),
    )
