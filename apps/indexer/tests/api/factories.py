"""API テスト用の、リクエスト JSON と設定のファクトリ。"""

import base64
import hashlib
from typing import Any

from loreley_indexer.config import Settings
from tests.crawl_runs.factories import CRAWL_ID, SOURCE_ID, hex_id
from tests.documents.factories import LOCK_OWNER

CRAWL_STARTED_AT_JSON = "2026-11-09T01:00:00Z"
FINISHED_AT_JSON = "2026-11-09T01:12:30Z"

# 小さな上限で、サイズ・件数の防御を少ないデータで確かめる。
MAX_RAW_BYTES = 1024
MAX_BATCH_BYTES = 2048
MAX_BATCH_DOCUMENTS = 3
MAX_REQUEST_BODY_BYTES = 64 * 1024
MAX_LAST_SEEN_IDS = 3


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "opensearch_url": "http://opensearch:9200",
        "max_raw_bytes": MAX_RAW_BYTES,
        "max_batch_bytes": MAX_BATCH_BYTES,
        "max_batch_documents": MAX_BATCH_DOCUMENTS,
        "max_request_body_bytes": MAX_REQUEST_BODY_BYTES,
        "max_last_seen_ids": MAX_LAST_SEEN_IDS,
        "max_content_bytes": 100,
        # ワーカーを待たずに済むよう、走査は起床通知で進める。
        "deletion_poll_interval_seconds": 30.0,
        "deletion_batch_size": 3,
        **overrides,
    }
    return Settings(_env_file=None, **values)


def lock_json(**overrides: Any) -> dict[str, Any]:
    return {"owner": LOCK_OWNER, "job_id": CRAWL_ID, **overrides}


def start_json(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "crawl_id": CRAWL_ID,
        "source_id": SOURCE_ID,
        "crawl_started_at": CRAWL_STARTED_AT_JSON,
        "ttl": 86_400,
        "ratio_threshold": 0.2,
        "min_delete_count": 10,
        "force_delete": False,
    }
    return {**body, **overrides}


def finish_json(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source_id": SOURCE_ID,
        "outcome": "enumeration_completed",
        "enumerated_count": 3,
        "skipped_document_ids": [hex_id(2), hex_id(1)],
        "skipped_count": 2,
        "oversize_document_ids": [],
        "finished_at": FINISHED_AT_JSON,
    }
    return {**body, **overrides}


def encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def document_json(
    external_id: str = "docs/a.txt", text: str = "hello\nworld\n", **overrides: Any
) -> dict[str, Any]:
    raw = text.encode("utf-8")
    body: dict[str, Any] = {
        "external_id": external_id,
        "title": "A",
        "mime_type": "text/plain",
        "raw_content": encode(raw),
        "content_hash": hashlib.sha256(raw).hexdigest(),
        "source_updated_at": "2026-11-08T12:00:00Z",
        "size": len(raw),
    }
    return {**body, **overrides}


def batch_json(documents: list[dict[str, Any]] | None = None, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "crawl_id": CRAWL_ID,
        "crawl_started_at": CRAWL_STARTED_AT_JSON,
        "lock": lock_json(),
        "documents": documents if documents is not None else [document_json()],
    }
    return {**body, **overrides}


def last_seen_json(document_ids: list[str], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "crawl_id": CRAWL_ID,
        "crawl_started_at": CRAWL_STARTED_AT_JSON,
        "lock": lock_json(),
        "document_ids": document_ids,
    }
    return {**body, **overrides}


def locked_json(**overrides: Any) -> dict[str, Any]:
    return {"lock": lock_json(), **overrides}


BATCH_PATH = f"/sources/{SOURCE_ID}/documents:batch"
LAST_SEEN_PATH = f"/sources/{SOURCE_ID}/last-seen"
DISCARD_PATH = f"/sources/{SOURCE_ID}/deletions:discard"
DELETE_DOCUMENTS_PATH = f"/sources/{SOURCE_ID}/documents"
DELETE_RECORDS_PATH = f"/sources/{SOURCE_ID}/deletion-records"
START_PATH = "/crawls/start"
FINISH_PATH = f"/crawls/{CRAWL_ID}/finish"
STATUS_PATH = f"/crawls/{CRAWL_ID}"
