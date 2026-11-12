"""ドメインの結果から、応答の JSON への写像(api 4.2〜4.5)。"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from loreley_indexer.common.timestamps import format_instant
from loreley_indexer.crawl_runs import CrawlStatus
from loreley_indexer.documents import (
    DocumentFailed,
    DocumentOutcome,
    DocumentRegistered,
    LastSeenEntry,
)


def start_response(crawl_id: str) -> dict[str, Any]:
    return {"crawl_id": crawl_id, "status": "running"}


def batch_response(outcomes: Sequence[DocumentOutcome]) -> dict[str, Any]:
    return {"results": [_document_result(outcome) for outcome in outcomes]}


def _document_result(outcome: DocumentOutcome) -> dict[str, Any]:
    match outcome:
        case DocumentRegistered():
            return {
                "external_id": outcome.external_id,
                "document_id": outcome.document_id,
                "status": "ok",
                "change": outcome.change.value,
                "extract_failed": outcome.extract_failed,
            }
        case DocumentFailed():
            return {
                "external_id": outcome.external_id,
                "document_id": outcome.document_id,
                "status": "failed",
                "failure_type": outcome.failure_type.value,
                "message": outcome.message,
            }


def last_seen_response(entries: Sequence[LastSeenEntry]) -> dict[str, Any]:
    return {
        "results": [
            {"document_id": entry.document_id, "result": entry.result.value} for entry in entries
        ]
    }


def status_response(status: CrawlStatus) -> dict[str, Any]:
    """値のない項目(未記録・該当しない)は、キーごと省く。"""
    fields: dict[str, Any] = {
        "crawl_id": status.crawl_id,
        "source_id": status.source_id,
        "status": status.status.value,
        "reason": status.reason.value if status.reason is not None else None,
        "forced": status.forced,
        "target_count": status.target_count,
        "denominator": status.denominator,
        "ttl": status.ttl,
        "ratio_threshold": status.ratio_threshold,
        "min_delete_count": status.min_delete_count,
        "deleted_count": status.deleted_count,
        "enumerated_count": status.enumerated_count,
        "n_seen": status.n_seen,
        "e_missing": status.e_missing,
        "finish_received_at": _instant(status.finish_received_at),
        "deletion_started_at": _instant(status.deletion_started_at),
        "finished_at": _instant(status.finished_at),
        "waiting_for": status.waiting_for,
    }
    return {name: value for name, value in fields.items() if value is not None}


def _instant(value: datetime | None) -> str | None:
    return format_instant(value) if value is not None else None
