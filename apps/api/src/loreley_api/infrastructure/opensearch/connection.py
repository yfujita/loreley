"""OpenSearch クライアントの生成(C 3.7。D 4.8 の 3 層目)。`main.py` だけが呼ぶ。

2 つのクライアントを起動時に作る(**接続はしない**。OpenSearch が落ちていても起動する)。
- 読み取り用: Reader が使う。再試行は `max_retries` まで(接続エラー・`retry_on_status`)。
  読み取りのタイムアウトは再試行しない。
- プローブ用: `cluster.health` だけ(EP-13)。短いタイムアウトで、再試行しない。

生のクライアントはここで許可リストのラッパーに包み、外へ出さない(閉じる関数だけ返す)。
ノードの探索(sniff)はしない。
"""

from collections.abc import Callable
from dataclasses import dataclass

from opensearchpy import OpenSearch

from loreley_api.infrastructure.opensearch.config import OpenSearchConnectionConfig
from loreley_api.infrastructure.opensearch.readonly_client import ReadOnlyOpenSearch

# A 5.6 の「429・5xx」より狭く、再試行の意味がある 5 値に限る(C 3.7)。
READ_RETRY_ON_STATUS = (429, 500, 502, 503, 504)
# `opensearch` の枠(16)・`probe` の枠(8)と同じ(C 8.1)。
READ_POOL_MAXSIZE = 16
PROBE_POOL_MAXSIZE = 8


@dataclass(frozen=True)
class ReadOnlyConnection:
    client: ReadOnlyOpenSearch
    close: Callable[[], None]


def create_read_connection(config: OpenSearchConnectionConfig) -> ReadOnlyConnection:
    return _create(
        config,
        timeout_seconds=config.request_timeout_seconds,
        max_retries=config.max_retries,
        retry_on_status=READ_RETRY_ON_STATUS,
        pool_maxsize=READ_POOL_MAXSIZE,
    )


def create_probe_connection(config: OpenSearchConnectionConfig) -> ReadOnlyConnection:
    return _create(
        config,
        timeout_seconds=config.probe_timeout_seconds,
        max_retries=0,
        retry_on_status=(),
        pool_maxsize=PROBE_POOL_MAXSIZE,
    )


def _create(
    config: OpenSearchConnectionConfig,
    *,
    timeout_seconds: float,
    max_retries: int,
    retry_on_status: tuple[int, ...],
    pool_maxsize: int,
) -> ReadOnlyConnection:
    http_auth = None
    if config.username is not None and config.password is not None:
        http_auth = (config.username, config.password)
    raw_client = OpenSearch(
        hosts=[config.url],
        http_auth=http_auth,
        verify_certs=config.verify_certs,
        ca_certs=config.ca_certs_path,
        timeout=timeout_seconds,
        max_retries=max_retries,
        # 読み取りのタイムアウトは再試行しない(A 5.6)。
        retry_on_timeout=False,
        retry_on_status=retry_on_status,
        pool_maxsize=pool_maxsize,
    )
    return ReadOnlyConnection(client=ReadOnlyOpenSearch(raw_client), close=raw_client.close)
