"""登録・`last-seen` のテスト用ファクトリ。"""

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from loreley_indexer.documents import CrawlContext, DocumentInput, DocumentRegistrar, LockInfo
from loreley_indexer.documents.document_id import compute_document_id
from tests.crawl_runs.factories import CRAWL_ID, CRAWL_STARTED_AT, SOURCE_ID
from tests.fakes.clock import DEFAULT_NOW
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore

LOCK_OWNER = "crawler-1"
SOURCE_UPDATED_AT = datetime(2026, 11, 8, 12, 0, 0, tzinfo=UTC)
NEWER_CRAWL_STARTED_AT = CRAWL_STARTED_AT + timedelta(days=1)


def make_context(**overrides: Any) -> CrawlContext:
    base = CrawlContext(
        source_id=SOURCE_ID,
        crawl_id=CRAWL_ID,
        crawl_started_at=CRAWL_STARTED_AT,
        lock=LockInfo(owner=LOCK_OWNER, job_id=CRAWL_ID),
    )
    return replace(base, **overrides)


def make_document(
    external_id: str = "docs/a.txt", text: str = "hello\nworld\n", **overrides: Any
) -> DocumentInput:
    raw_content = overrides.pop("raw_content", text.encode("utf-8"))
    base: dict[str, Any] = {
        "external_id": external_id,
        "title": "A",
        "mime_type": "text/plain",
        "raw_content": raw_content,
        "content_hash": hashlib.sha256(raw_content).hexdigest(),
        "source_updated_at": SOURCE_UPDATED_AT,
        "size": len(raw_content),
        "url": None,
        "path": None,
    }
    return DocumentInput(**{**base, **overrides})


def id_of(document: DocumentInput | str, source_id: str = SOURCE_ID) -> str:
    external_id = document if isinstance(document, str) else document.external_id
    return compute_document_id(source_id, external_id)


def register_one(registrar: DocumentRegistrar, document: DocumentInput, **context: Any):
    """1 件だけ登録して、その結果を返す。`context` は `make_context` の上書き。"""
    [outcome] = registrar.register(make_context(**context), [document])
    return outcome


def seed_lock(
    jobs_store: InMemoryStore,
    *,
    source_id: str = SOURCE_ID,
    owner: str = LOCK_OWNER,
    job_id: str = CRAWL_ID,
    lease_expires_at: datetime = DEFAULT_NOW + timedelta(hours=1),
) -> None:
    jobs_store.seed(
        f"lock-{source_id}",
        {
            "owner": owner,
            "job_id": job_id,
            "lease_expires_at": lease_expires_at.isoformat(),
        },
    )


def set_maintenance(jobs_store: InMemoryStore, *, enabled: bool) -> None:
    jobs_store.seed("maintenance", {"enabled": enabled})


# 文書はあるが `enabled` が真偽値で明示されていない形(fail-closed で「立っている」。0014)。
MALFORMED_MAINTENANCE_BODIES = [
    pytest.param({"enabled": "true"}, id="string-true"),
    pytest.param({"enabled": "false"}, id="string-false"),
    pytest.param({"enabled": 1}, id="one"),
    pytest.param({"enabled": 0}, id="zero"),
    pytest.param({"enabled": None}, id="null"),
    pytest.param({"enabled": ""}, id="empty-string"),
    pytest.param({"enabled": []}, id="empty-list"),
    pytest.param({"enabled": {}}, id="empty-object"),
    pytest.param({"enabled": 0.0}, id="zero-float"),
    pytest.param({"enabled": 1.0}, id="one-float"),
    pytest.param({}, id="empty"),
    pytest.param({"other": False}, id="enabled-missing"),
]


def set_malformed_maintenance(jobs_store: InMemoryStore, body: dict[str, Any]) -> None:
    jobs_store.seed("maintenance", body)


def stored_document(
    search_index: InMemorySearchIndex, document: DocumentInput | str
) -> dict[str, Any]:
    source = search_index.source_of(id_of(document))
    assert source is not None, "the document is not in the index"
    return source


def source_of(search_index: InMemorySearchIndex, document_id: str) -> dict[str, Any]:
    """文書 ID で直接引く(`stored_document` は入力から ID を算出する)。"""
    source = search_index.source_of(document_id)
    assert source is not None, "the document is not in the index"
    return source


def status_of(search_index: InMemorySearchIndex, document_id: str) -> str:
    """`summary_status`。"""
    return source_of(search_index, document_id)["summary_status"]
