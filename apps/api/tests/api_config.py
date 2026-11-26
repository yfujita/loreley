"""テスト用の `ApiConfig`(環境変数を読まずに作る。`test_config.py` 以外が使う)。"""

import dataclasses

from loreley_api.admin import AdminSettings
from loreley_api.config import ApiConfig
from loreley_api.infrastructure.crawler_client import CrawlerClientConfig
from loreley_api.infrastructure.opensearch import IndexNames, OpenSearchConnectionConfig
from loreley_api.infrastructure.probes import HttpProbeConfig

SENTINEL_PASSWORD = "SENTINEL-OPENSEARCH-PASSWORD"


def make_admin_settings(**overrides: object) -> AdminSettings:
    settings = AdminSettings(
        crawler_url="http://crawler.invalid:8001",
        indexer_url="http://indexer.invalid:8000",
        web_url="http://web.invalid:80",
        dashboards_health_url=None,
        embedding_health_url=None,
        llm_health_url=None,
        probe_timeout_seconds=3.0,
        cron_timezone="Asia/Tokyo",
        dashboards_url=None,
        admitting_lock_grace_seconds=60.0,
        openapi_enabled=False,
    )
    return dataclasses.replace(settings, **overrides)


def make_api_config(**overrides: object) -> ApiConfig:
    """既定は、どこにも接続できない `.invalid` のホスト(接続を試みたら失敗する)。"""
    config = ApiConfig(
        host="127.0.0.1",
        port=8080,
        log_level="INFO",
        opensearch=OpenSearchConnectionConfig(
            url="http://opensearch.invalid:9200",
            username="user",
            password=SENTINEL_PASSWORD,
            verify_certs=True,
            ca_certs_path=None,
            request_timeout_seconds=10.0,
            max_retries=2,
            probe_timeout_seconds=3.0,
        ),
        index_names=IndexNames(
            sources="loreley-sources",
            jobs="loreley-jobs",
            deletions="loreley-deletions",
            search="loreley-documents",
        ),
        crawler_client=CrawlerClientConfig(
            base_url="http://crawler.invalid:8001",
            connect_timeout_seconds=3.0,
            response_timeout_seconds=60.0,
        ),
        http_probe=HttpProbeConfig(timeout_seconds=3.0),
        admin=make_admin_settings(),
    )
    return dataclasses.replace(config, **overrides)
