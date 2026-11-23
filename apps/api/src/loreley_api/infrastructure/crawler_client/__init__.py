"""Crawler の 6 API を固定の経路で呼ぶクライアント(D 4.9)。

入口は、設定の型(`config.py` がこの入口だけを import する)。クライアント本体は未実装。
"""

from loreley_api.infrastructure.crawler_client.config import CrawlerClientConfig

__all__ = ["CrawlerClientConfig"]
