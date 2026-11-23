"""失敗した読み取りが、ID・パスワード・パスをログに出さないこと(C 8.5。A 5.5)。

DEBUG でも、実際に接続に失敗させて確かめる(接続先は、名前解決できない `.invalid`)。
"""

import io
import logging
from dataclasses import replace

import pytest

from loreley_api.common.logging_setup import configure_logging
from loreley_api.common.results import Failed
from loreley_api.infrastructure.opensearch import OpenSearchJobsReader, create_read_connection
from tests.api_config import SENTINEL_PASSWORD, make_api_config
from tests.secret_assertions import assert_secret_absent

SENTINEL_JOB_ID = "SENTINEL-JOB-ID"
SENTINEL_INDEX_PATH = "SENTINEL-INDEX-PATH"


class RecordsCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.mark.usefixtures("restore_logging")
def test_a_real_connection_failure_at_debug_logs_no_id_password_or_path() -> None:
    stream = io.StringIO()
    configure_logging(level="DEBUG", stream=stream)
    collector = RecordsCollector()
    logging.getLogger().addHandler(collector)
    config = replace(make_api_config().opensearch, max_retries=0, request_timeout_seconds=3.0)
    connection = create_read_connection(config)
    reader = OpenSearchJobsReader(connection.client, jobs_index=SENTINEL_INDEX_PATH)

    try:
        results = reader.get_jobs([SENTINEL_JOB_ID], ["job_id"])
    finally:
        connection.close()

    assert isinstance(results[SENTINEL_JOB_ID], Failed)  # 実際に失敗した
    captured_text = stream.getvalue()
    assert "opensearch read failed" in captured_text  # 失敗のログは出ている(捕捉できている)
    for secret in (SENTINEL_PASSWORD, SENTINEL_JOB_ID, SENTINEL_INDEX_PATH):
        assert_secret_absent(secret, records=collector.records, captured_text=captured_text)
