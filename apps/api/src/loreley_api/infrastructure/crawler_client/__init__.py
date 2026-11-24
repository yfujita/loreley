"""Crawler の 6 API を固定の経路で呼ぶクライアント(D 4.9)。

`admin` が import するのは、`client` の Protocol と返り値の型だけ(R6)。`main.py` は、設定の型と
`HttpCrawlerClient` の生成・`close` だけを使う。
"""

from loreley_api.infrastructure.crawler_client.client import (
    ConfigInvalidMessage,
    ConfigViolation,
    CrawlerClient,
    CrawlerContractViolation,
    CrawlerRejected,
    CrawlerReply,
    CrawlerResult,
    CrawlerSourceSettings,
    CrawlerSucceeded,
    CrawlerTransportFailed,
)
from loreley_api.infrastructure.crawler_client.config import CrawlerClientConfig
from loreley_api.infrastructure.crawler_client.http_client import HttpCrawlerClient

__all__ = [
    "ConfigInvalidMessage",
    "ConfigViolation",
    "CrawlerClient",
    "CrawlerClientConfig",
    "CrawlerContractViolation",
    "CrawlerRejected",
    "CrawlerReply",
    "CrawlerResult",
    "CrawlerSourceSettings",
    "CrawlerSucceeded",
    "CrawlerTransportFailed",
    "HttpCrawlerClient",
]
