"""Crawler クライアント(Protocol)の偽物(D 7.2)。

`services` のテストで、HTTP の層(`crawler_client` の本物)を持ち込まずに、台本の返り値と呼び出しの
記録を使う。HTTP の層は、ローカル HTTP スタブを使う `infrastructure/crawler_client/` のテストが
確かめる。

- 返り値の差し替え: `client.behavior.inject("start_crawl", CrawlerRejected(...))`
  (`CrawlerSucceeded`・`CrawlerRejected`・`CrawlerTransportFailed`・`CrawlerContractViolation`。
  `times` で回数、`key`(`source_id`・`job_id`)で対象を絞れる)。差し替えがなければ、操作ごとの
  既定の成功を返す。
- 呼び出しの記録: `client.requests`(操作名と引数)。`client.behavior.calls_of(...)` は回数だけ。
- 呼び出しの直前の割り込み: `client.behavior.before("start_crawl", callback)`。

操作名は `OPERATIONS` にあるものだけで、それ以外(打ち間違い)は `ValueError`。Protocol のメソッドと
過不足がないことは `test_fake_crawler_client_protocol.py` が確かめる。
"""

from dataclasses import dataclass
from typing import Any

from loreley_api.infrastructure.crawler_client import (
    CrawlerResult,
    CrawlerSourceSettings,
    CrawlerSucceeded,
)
from tests.fakes.behavior import FakeBehavior

OPERATIONS = frozenset(
    {
        "register_source",
        "update_source",
        "start_delete_job",
        "start_crawl",
        "cancel_job",
        "release_lock",
    }
)


@dataclass(frozen=True)
class RecordedRequest:
    operation: str
    arguments: dict[str, Any]


def _source_body(source_id: str, settings: CrawlerSourceSettings) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "connector_type": "file_system",
        "connector_config": settings.connector_config,
        "ttl": settings.ttl_seconds,
        "ratio_threshold": settings.ratio_threshold,
        "min_delete_count": settings.min_delete_count,
        "schedule_cron": settings.schedule_cron,
        "status": "active",
        "updated_at": "2026-11-24T00:00:00.000Z",
    }


def _accepted_body(source_id: str, job_type: str, options: dict[str, bool]) -> dict[str, Any]:
    return {
        "job_id": "job-20261124T000000Z-0000aaaa",
        "job_type": job_type,
        "source_id": source_id,
        "status": "queued",
        "trigger": "manual",
        **options,
        "queued_at": "2026-11-24T00:00:00.000Z",
    }


class FakeCrawlerClient:
    def __init__(self) -> None:
        self.behavior = FakeBehavior(known_operations=OPERATIONS)
        self.requests: list[RecordedRequest] = []

    def register_source(
        self, source_id: str, connector_type: str, settings: CrawlerSourceSettings
    ) -> CrawlerResult:
        self._record(
            "register_source",
            source_id=source_id,
            connector_type=connector_type,
            settings=settings,
        )
        return self._reply(
            "register_source", source_id, CrawlerSucceeded(201, _source_body(source_id, settings))
        )

    def update_source(self, source_id: str, settings: CrawlerSourceSettings) -> CrawlerResult:
        self._record("update_source", source_id=source_id, settings=settings)
        return self._reply(
            "update_source", source_id, CrawlerSucceeded(200, _source_body(source_id, settings))
        )

    def start_delete_job(self, source_id: str) -> CrawlerResult:
        self._record("start_delete_job", source_id=source_id)
        body = _accepted_body(source_id, "source_delete", {})
        return self._reply("start_delete_job", source_id, CrawlerSucceeded(202, body))

    def start_crawl(
        self, source_id: str, *, force_delete: bool, rewrite_mode: bool
    ) -> CrawlerResult:
        self._record(
            "start_crawl",
            source_id=source_id,
            force_delete=force_delete,
            rewrite_mode=rewrite_mode,
        )
        options = {"force_delete": force_delete, "rewrite_mode": rewrite_mode}
        body = _accepted_body(source_id, "crawl", options)
        return self._reply("start_crawl", source_id, CrawlerSucceeded(202, body))

    def cancel_job(self, job_id: str) -> CrawlerResult:
        self._record("cancel_job", job_id=job_id)
        body = {"job_id": job_id, "status": "cancelled"}
        return self._reply("cancel_job", job_id, CrawlerSucceeded(200, body))

    def release_lock(self, source_id: str) -> CrawlerResult:
        self._record("release_lock", source_id=source_id)
        body = {"source_id": source_id, "released": True, "failed_job_id": None}
        return self._reply("release_lock", source_id, CrawlerSucceeded(200, body))

    def _record(self, operation: str, **arguments: Any) -> None:
        self.requests.append(RecordedRequest(operation, arguments))

    def _reply(self, operation: str, key: str, default: CrawlerResult) -> CrawlerResult:
        intercepted = self.behavior.enter(operation, key)
        return default if intercepted is None else intercepted.value
