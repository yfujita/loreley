from dataclasses import dataclass


@dataclass(frozen=True)
class AdminSettings:
    """Admin API 固有の設定(C 7.2)。値の検証は `config.py` が済ませている。"""

    # Crawler・Indexer の接続先(末尾の `/` を取り除いた `scheme://host[:port]`)。EP-13 が
    # `/healthz` を確認する。操作の呼び出しに使う Crawler の URL は `CrawlerClientConfig` が持つ。
    crawler_url: str
    indexer_url: str
    # `web` コンテナ(Nginx)の接続先。EP-13 が `/admin/` を確認する(同じ形)。
    web_url: str
    # 任意コンポーネントの確認先(完全な URL)。`None` は未設定(`not_configured`)。
    dashboards_health_url: str | None
    embedding_health_url: str | None
    llm_health_url: str | None
    # 確認 1 件のタイムアウト。EP-13 全体の期限は、これに 1 秒を足した値(C 6.1)。
    probe_timeout_seconds: float
    # EP-14。`None` は未設定(`null` で返す)。
    cron_timezone: str | None
    dashboards_url: str | None
    # `just_acquired` の猶予。Crawler の `ADMITTING_LOCK_GRACE_SECONDS` と同じ値(C 5.9)。
    admitting_lock_grace_seconds: float
    openapi_enabled: bool
