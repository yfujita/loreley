from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from loreley_crawler.infrastructure.indexer_client import (
    DocumentToRegister,
    FinishOutcome,
    HttpIndexerClient,
    IndexerClientConfig,
    LockInfo,
)
from tests.fakes.local_http_server import LocalServer, Reply, local_http_server

LOCK = LockInfo(owner="crawler-1", job_id="job-20261113-0a1b2c3d")
CRAWL_ID = "job-20261113-0a1b2c3d"
SOURCE_ID = "src-docs"
CRAWL_STARTED_AT = datetime(2026, 11, 13, 1, 2, 3, 456000, tzinfo=UTC)
DOCUMENT_ID = "6b5851d90534fc00e388eeb8bd8c79ae48b8bf5c58e4fb0191e708afa28674d7"
CONTENT_HASH = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def make_document(**overrides: object) -> DocumentToRegister:
    fields: dict[str, object] = {
        "external_id": "docs/setup.md",
        "title": "setup.md",
        "mime_type": "text/markdown",
        "raw_content": b"hello",
        "content_hash": CONTENT_HASH,
        "source_updated_at": datetime(2026, 11, 8, 12, 0, 0, tzinfo=UTC),
        "size": 5,
    }
    fields.update(overrides)
    return DocumentToRegister(**fields)


Operation = Callable[[HttpIndexerClient], object]

# 全 API を、最小の引数で 1 回ずつ呼ぶ操作。`last_seen`・`batch` は、要請の `document_id`・
# `external_id` と応答の対応を照合するので、これらの値(`DOCUMENT_ID`・`EXTERNAL_ID`)に合わせた
# 応答を返すこと。
EXTERNAL_ID = "docs/setup.md"

OPERATIONS: dict[str, Operation] = {
    "start": lambda c: c.start_crawl(
        crawl_id=CRAWL_ID,
        source_id=SOURCE_ID,
        crawl_started_at=CRAWL_STARTED_AT,
        ttl=1,
        ratio_threshold=0.5,
        min_delete_count=1,
        force_delete=False,
        rewrite_mode=False,
    ),
    "last_seen": lambda c: c.report_last_seen(
        SOURCE_ID,
        crawl_id=CRAWL_ID,
        crawl_started_at=CRAWL_STARTED_AT,
        lock=LOCK,
        document_ids=[DOCUMENT_ID],
    ),
    "batch": lambda c: c.register_documents(
        SOURCE_ID,
        crawl_id=CRAWL_ID,
        crawl_started_at=CRAWL_STARTED_AT,
        lock=LOCK,
        documents=[make_document(external_id=EXTERNAL_ID)],
    ),
    "finish": lambda c: c.finish_crawl(
        CRAWL_ID, source_id=SOURCE_ID, outcome=FinishOutcome.FAILED, finished_at=CRAWL_STARTED_AT
    ),
    "status": lambda c: c.get_crawl_status(CRAWL_ID),
    "discard": lambda c: c.discard_deletions(SOURCE_ID, lock=LOCK),
    "delete_documents": lambda c: c.delete_documents(SOURCE_ID, lock=LOCK),
    "delete_records": lambda c: c.delete_deletion_records(SOURCE_ID, lock=LOCK),
}


@contextmanager
def serving(reply: Reply) -> Iterator[tuple[HttpIndexerClient, LocalServer]]:
    """どのリクエストにも `reply` を返すサーバと、それにつないだクライアント。"""
    with local_http_server(lambda request: reply) as server:
        client = HttpIndexerClient(IndexerClientConfig(server.url))
        try:
            yield client, server
        finally:
            client.close()


def call_with(reply: Reply, operation: Operation) -> object:
    with serving(reply) as (client, _server):
        return operation(client)


def batch_of(*external_ids: str) -> Operation:
    """指定した `external_id` の文書を、この順に登録する操作。"""
    return lambda c: c.register_documents(
        SOURCE_ID,
        crawl_id=CRAWL_ID,
        crawl_started_at=CRAWL_STARTED_AT,
        lock=LOCK,
        documents=[make_document(external_id=external_id) for external_id in external_ids],
    )


def last_seen_of(*document_ids: str) -> Operation:
    """指定した `document_id` を、この順に `last-seen` で要請する操作。"""
    return lambda c: c.report_last_seen(
        SOURCE_ID,
        crawl_id=CRAWL_ID,
        crawl_started_at=CRAWL_STARTED_AT,
        lock=LOCK,
        document_ids=list(document_ids),
    )
