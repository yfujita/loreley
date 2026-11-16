"""ログ・結果・`repr` に、本文・秘密・Indexer のエラーメッセージを出さない(R11。完了条件 8)。

`urllib3` は DEBUG でリクエストのパス(`source_id`・`crawl_id` を含む)を出す。`common/log_setup` の
制限(ERROR 以上に固定)が効いていることを、実際の通信を通して確かめる。
"""

import io
import logging
from datetime import UTC, datetime

import pytest

from loreley_crawler.common.log_setup import configure_logging
from loreley_crawler.infrastructure.indexer_client import (
    FinishOutcome,
    HttpIndexerClient,
    IndexerClientConfig,
    LockInfo,
)
from tests.fakes.local_http_server import Reply, local_http_server
from tests.infrastructure.indexer_client.support import make_document

SENTINEL_CONTENT = "SENTINEL-RAW-CONTENT"
SENTINEL_SOURCE = "SENTINEL-SOURCE-ID"
SENTINEL_MESSAGE = "SENTINEL-INDEXER-MESSAGE"
SENTINEL_TITLE = "SENTINEL-TITLE"
NOW = datetime(2026, 11, 13, tzinfo=UTC)
LOCK = LockInfo(owner="crawler-1", job_id="job-1")


def call_every_api(client: HttpIndexerClient) -> list[object]:
    document = make_document(
        raw_content=SENTINEL_CONTENT.encode(), title=SENTINEL_TITLE, size=len(SENTINEL_CONTENT)
    )
    return [
        client.report_last_seen(
            SENTINEL_SOURCE, crawl_id="job-1", crawl_started_at=NOW, lock=LOCK, document_ids=[]
        ),
        client.register_documents(
            SENTINEL_SOURCE, crawl_id="job-1", crawl_started_at=NOW, lock=LOCK, documents=[document]
        ),
        client.finish_crawl(
            "job-1", source_id=SENTINEL_SOURCE, outcome=FinishOutcome.FAILED, finished_at=NOW
        ),
        client.get_crawl_status("job-1"),
        client.discard_deletions(SENTINEL_SOURCE, lock=LOCK),
        client.delete_documents(SENTINEL_SOURCE, lock=LOCK),
        client.delete_deletion_records(SENTINEL_SOURCE, lock=LOCK),
    ]


def error_reply() -> Reply:
    return Reply(
        status=409,
        body={"error": {"code": "lock_not_owned", "message": SENTINEL_MESSAGE, "retryable": False}},
    )


def test_urllib3_logs_the_request_path_when_it_is_not_restricted() -> None:
    """制御実験: 制限しなければ、実際にパスの ID がログに出る(制限が必要なことの確認)。"""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    urllib3_logger = logging.getLogger("urllib3")
    saved_level = urllib3_logger.level
    urllib3_logger.setLevel(logging.DEBUG)
    urllib3_logger.addHandler(handler)
    try:
        with local_http_server(lambda request: error_reply()) as server:
            call_every_api(HttpIndexerClient(IndexerClientConfig(server.url)))
    finally:
        urllib3_logger.removeHandler(handler)
        urllib3_logger.setLevel(saved_level)

    assert SENTINEL_SOURCE in stream.getvalue()


@pytest.mark.usefixtures("restore_logging")
def test_nothing_sensitive_reaches_the_log_even_at_debug_level() -> None:
    stream = io.StringIO()
    configure_logging(level=logging.DEBUG, secrets=[], stream=stream)

    with local_http_server(lambda request: error_reply()) as server:
        call_every_api(HttpIndexerClient(IndexerClientConfig(server.url)))

    logged = stream.getvalue()
    for sentinel in (SENTINEL_CONTENT, SENTINEL_SOURCE, SENTINEL_MESSAGE, SENTINEL_TITLE):
        assert sentinel not in logged


@pytest.mark.usefixtures("restore_logging")
def test_nothing_sensitive_reaches_the_log_when_the_connection_fails() -> None:
    stream = io.StringIO()
    configure_logging(level=logging.DEBUG, secrets=[], stream=stream)

    with local_http_server(lambda request: Reply(disconnect=True)) as server:
        call_every_api(HttpIndexerClient(IndexerClientConfig(server.url)))

    logged = stream.getvalue()
    for sentinel in (SENTINEL_CONTENT, SENTINEL_SOURCE, SENTINEL_TITLE):
        assert sentinel not in logged


def test_results_never_carry_the_request_or_the_indexer_message() -> None:
    with local_http_server(lambda request: error_reply()) as server:
        results = call_every_api(HttpIndexerClient(IndexerClientConfig(server.url)))

    text = "\n".join(repr(result) for result in results)
    for sentinel in (SENTINEL_CONTENT, SENTINEL_SOURCE, SENTINEL_MESSAGE, SENTINEL_TITLE):
        assert sentinel not in text


def test_the_repr_of_a_document_to_register_hides_the_raw_content() -> None:
    document = make_document(raw_content=SENTINEL_CONTENT.encode())

    assert SENTINEL_CONTENT not in repr(document)
    assert "raw_content" not in repr(document)


def test_the_client_writes_nothing_to_the_log_itself(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="loreley_crawler")

    with local_http_server(lambda request: error_reply()) as server:
        call_every_api(HttpIndexerClient(IndexerClientConfig(server.url)))

    assert [r for r in caplog.records if r.name.startswith("loreley_crawler")] == []
