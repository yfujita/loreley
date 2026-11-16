"""`jobs/records` のテストの共通部品。"""

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any

from loreley_crawler.common.retry import Retrier, RetryPolicy
from loreley_crawler.infrastructure.opensearch import (
    BulkDeleteResult,
    RecordFilter,
    RecordPages,
    RepositorySettings,
    SortKey,
)
from loreley_crawler.jobs.records import JobTrigger, JobType, new_queued_job_fields
from tests.fakes.clock import DEFAULT_NOW
from tests.fakes.in_memory_repository import InMemoryRepository

OWNER = "crawler-1"

# 待たずに、決定的にリトライする(試行 3 回)。
NO_WAIT_RETRIER = Retrier(
    RetryPolicy(3, 0.0, 1.0, 0.0, 0.0), sleep=lambda _seconds: None, wait_slice_seconds=1_000
)


class SpyRepository(InMemoryRepository):
    """走査の条件・並べ替えと、バルク削除に渡した ID を記録する。"""

    def __init__(self, settings: RepositorySettings | None = None) -> None:
        super().__init__(settings)
        self.scans: list[tuple[RecordFilter, tuple[SortKey, ...]]] = []
        self.deleted_id_batches: list[tuple[str, ...]] = []

    def scan(
        self, record_filter: RecordFilter, *, sort: Sequence[SortKey]
    ) -> AbstractContextManager[RecordPages]:
        self.scans.append((record_filter, tuple(sort)))
        return super().scan(record_filter, sort=sort)

    def delete_ids(self, record_ids: Sequence[str]) -> BulkDeleteResult:
        self.deleted_id_batches.append(tuple(record_ids))
        return super().delete_ids(record_ids)


def job_fields(job_id: str = "job-20261113T000000Z-00000001", **overrides: Any) -> dict[str, Any]:
    fields = new_queued_job_fields(
        job_id=job_id,
        job_type=JobType.CRAWL,
        source_id="docs",
        trigger=JobTrigger.MANUAL,
        owner=OWNER,
        force_delete=False,
        rewrite_mode=False,
        queued_at=DEFAULT_NOW,
    )
    fields.update(overrides)
    return fields


def document_record(
    record_type: str, source_id: str, document_id: str, **extra: Any
) -> Mapping[str, Any]:
    return {
        "record_type": record_type,
        "source_id": source_id,
        "document_id": document_id,
        "external_id": f"ext-{document_id}",
        "last_job_id": "job-old",
        **extra,
    }


def seed_document_record(
    repository: InMemoryRepository, record_type: str, source_id: str, document_id: str
) -> str:
    record_id = f"{record_type}-{source_id}-{document_id}"
    repository.seed(record_id, document_record(record_type, source_id, document_id))
    return record_id
