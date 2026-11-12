"""OpenSearch への接続設定とクライアントの生成。"""

from collections.abc import Collection
from contextlib import ExitStack
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from opensearchpy import OpenSearch

# 索引名は設計書で未決(arch U-6、U-7)。設定で変えられる仮名の既定値をここに隔離する。
DEFAULT_SEARCH_INDEX_NAME = "loreley-documents"
DEFAULT_DELETIONS_INDEX_NAME = "loreley-deletions"
DEFAULT_JOBS_INDEX_NAME = "loreley-jobs"

# `delete_by_query` は対象が多いと通常のリクエストより長くかかるため、専用のタイムアウトを持つ。
DEFAULT_DELETE_BY_QUERY_TIMEOUT_SECONDS = 600.0


# opensearch-py の既定値(通常のクライアントはこれまでどおり)。
DEFAULT_RETRY_ON_STATUS = (502, 503, 504)


@dataclass(frozen=True)
class IndexNames:
    search_index: str = DEFAULT_SEARCH_INDEX_NAME
    deletions: str = DEFAULT_DELETIONS_INDEX_NAME
    jobs: str = DEFAULT_JOBS_INDEX_NAME


@dataclass(frozen=True)
class OpenSearchConnectionConfig:
    url: str
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    verify_certs: bool = True
    ca_certs_path: str | None = None
    request_timeout_seconds: float = 30.0
    transport_max_retries: int = 2
    delete_by_query_timeout_seconds: float = DEFAULT_DELETE_BY_QUERY_TIMEOUT_SECONDS

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


def create_opensearch_client(config: OpenSearchConnectionConfig) -> OpenSearch:
    return _create_client(config)


def create_delete_by_query_client(config: OpenSearchConnectionConfig) -> OpenSearch:
    """`delete_by_query` 専用のクライアント。タイムアウトや 502/503/504 でも自動では再送しない。

    `delete_by_query` はサーバ側で処理が続くことがあり、クライアントの再送は同じ削除を重ねて
    走らせて負荷をかける。再実行するかは呼び出し側(ソース削除の再実行の上限)が決める。
    接続エラーは通常のクライアントと同じ回数だけ再送する(送信後に接続が切れた場合も
    接続エラーなので、リクエストが届いていたことはありうる)。`delete_by_query` は
    `conflicts=proceed` で、同じ条件を再実行しても安全(すでに消えた文書は対象にならない)。
    """
    return _create_client(config, retry_on_timeout=False, retry_on_status=())


def close_clients(*clients: OpenSearch) -> None:
    """クライアントの接続プールを閉じる。1 つの `close()` が失敗しても、残りを閉じる。"""
    with ExitStack() as stack:
        for client in clients:
            stack.callback(client.close)


def _create_client(
    config: OpenSearchConnectionConfig,
    *,
    retry_on_timeout: bool = True,
    retry_on_status: Collection[int] = DEFAULT_RETRY_ON_STATUS,
) -> OpenSearch:
    http_auth = None
    if config.username is not None and config.password is not None:
        http_auth = (config.username, config.password)
    return OpenSearch(
        hosts=[config.url],
        http_auth=http_auth,
        verify_certs=config.verify_certs,
        ca_certs=config.ca_certs_path,
        timeout=config.request_timeout_seconds,
        max_retries=config.transport_max_retries,
        retry_on_timeout=retry_on_timeout,
        retry_on_status=retry_on_status,
    )
