from loreley_indexer.common.errors import UnavailableError, UnexpectedResponseError


class OpenSearchUnavailableError(UnavailableError):
    """接続エラー、タイムアウト、401/403、429、5xx、cluster_block、circuit breaker、索引の不在など。

    `reason` は原因の種別名だけ(例: `connection_timeout`、`http_503`)。
    """


class OpenSearchUnexpectedResponseError(UnexpectedResponseError):
    """想定外の応答。クエリやマッピングの誤りなど、再試行で直らない異常(api では 500)。"""
