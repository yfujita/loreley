"""Crawler への呼び出しが、ID・`connector_config`・Crawler の `message` を出さないこと。

ログと返り値の両方を、DEBUG でも実際に呼び出して確かめる(C 8.5。A 5.5。R11)。
`config_invalid` の `message` だけは、B 2.5 のとおり返り値に載せる(`crawler_message`)ので対象外。
"""

import io
import json
import logging

import pytest

from loreley_api.common.logging_setup import configure_logging
from loreley_api.infrastructure.crawler_client import (
    CrawlerClientConfig,
    CrawlerSourceSettings,
    HttpCrawlerClient,
)
from tests.fakes.local_http_server import StubReply, closed_port, local_http_server
from tests.secret_assertions import assert_secret_absent

SENTINEL_SOURCE_ID = "SENTINEL-SOURCE-ID"
SENTINEL_JOB_ID = "SENTINEL-JOB-ID"
SENTINEL_ROOT = "/SENTINEL-ROOT-PATH"
SENTINEL_MESSAGE = "SENTINEL-CRAWLER-MESSAGE"
SECRETS = (SENTINEL_SOURCE_ID, SENTINEL_JOB_ID, SENTINEL_ROOT, SENTINEL_MESSAGE)

SETTINGS = CrawlerSourceSettings(
    connector_config={"root": SENTINEL_ROOT},
    ttl_seconds=86_400,
    ratio_threshold=0.2,
    min_delete_count=1,
    schedule_cron=None,
)


class RecordsCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.mark.usefixtures("restore_logging")
def test_calls_at_debug_log_no_id_connector_config_or_crawler_message() -> None:
    stream = io.StringIO()
    configure_logging(level="DEBUG", stream=stream)
    collector = RecordsCollector()
    logging.getLogger().addHandler(collector)
    rejection = {"error": {"code": "unavailable", "message": SENTINEL_MESSAGE, "retryable": True}}

    with local_http_server() as server:
        server.set_default_reply(StubReply(503, json.dumps(rejection).encode()))
        client = HttpCrawlerClient(CrawlerClientConfig(server.url, 3.0, 5.0))
        refused = HttpCrawlerClient(
            CrawlerClientConfig(f"http://127.0.0.1:{closed_port()}", 3.0, 5.0)
        )
        results = [
            client.register_source(SENTINEL_SOURCE_ID, "file_system", SETTINGS),
            client.update_source(SENTINEL_SOURCE_ID, SETTINGS),
            client.start_crawl(SENTINEL_SOURCE_ID, force_delete=False, rewrite_mode=False),
            client.cancel_job(SENTINEL_JOB_ID),
            refused.release_lock(SENTINEL_SOURCE_ID),
        ]

    captured_text = stream.getvalue()
    assert "crawler call: route=" in captured_text  # 呼び出しのログは出ている(捕捉できている)
    assert "/sources/{source_id}/lock" in captured_text  # テンプレートで出る
    for secret in SECRETS:
        assert_secret_absent(
            secret,
            response_text=repr(results),
            records=collector.records,
            captured_text=captured_text,
        )
