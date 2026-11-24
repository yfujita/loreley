from dataclasses import dataclass


@dataclass(frozen=True)
class CrawlerClientConfig:
    """Crawler への接続設定(C 4.1)。値の検証は `config.py` が済ませている。"""

    # 末尾の `/` を取り除いた `scheme://host[:port]`。固定のパスを足して使う。
    base_url: str
    connect_timeout_seconds: float
    response_timeout_seconds: float
