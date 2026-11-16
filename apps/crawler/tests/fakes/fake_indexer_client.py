"""`IndexerClient` の偽物(fake)。HTTP を使わず、呼び出しを記録して、応答を差し替えられる。

- 呼び出しの記録: すべての操作を、呼ばれた順に `calls` に残す(引数つき)。呼び出し順の検証
  (開始通知 -> `last-seen` -> バッチ登録 -> 終了通知。architecture 12章 #2)に使う。
- 既定の応答: 成功(開始通知・終了通知は `Succeeded`、`last-seen` は全件 `updated`、バッチ登録は全件
  `created`。`document_id` は `SHA-256(source_id + "\\0" + external_id)` で、`registration_failures`
  に載せた `external_id` は失敗)。Status は `deleted`。ソース削除は成功。
- 忠実度の限界(実 Indexer での確認は P9 に持ち越す): ソース削除 2・3(`delete_documents`・
  `delete_deletion_records`)は、実 Indexer のように `lock` の値(`owner`・`job_id`)を検証して
  409 `lock_not_owned` を返すことはしない(注入で再現する)。
- 応答の差し替え・エラーの注入・割り込みフック: `behavior`(操作名はこのモジュールの定数)。
  例: `fake.behavior.inject(REGISTER_DOCUMENTS, IndexerUnavailable("http_503"), times=2)`。
"""

import hashlib
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from loreley_crawler.common.timestamps import format_instant
from loreley_crawler.infrastructure.indexer_client import (
    BatchReply,
    BatchResults,
    Change,
    CrawlStatus,
    DeleteDocumentsReply,
    DeleteRecordsReply,
    DeletionRecordsDeleted,
    DiscardReply,
    DiscardResult,
    DocumentFailed,
    DocumentRegistered,
    DocumentsDeleted,
    DocumentToRegister,
    FailureType,
    FinishOutcome,
    FinishReply,
    IndexerClient,
    IndexerRejected,
    LastSeenEntry,
    LastSeenReply,
    LastSeenResult,
    LastSeenResults,
    LockInfo,
    StartReply,
    StatusReply,
    Succeeded,
    payloads,
)
from tests.fakes.behavior import FakeBehavior

START_CRAWL = "start_crawl"
REPORT_LAST_SEEN = "report_last_seen"
REGISTER_DOCUMENTS = "register_documents"
FINISH_CRAWL = "finish_crawl"
GET_CRAWL_STATUS = "get_crawl_status"
DISCARD_DELETIONS = "discard_deletions"
DELETE_DOCUMENTS = "delete_documents"
DELETE_DELETION_RECORDS = "delete_deletion_records"

# Indexer に書き込みを要請する操作(architecture 7.1。R8 で確認点を通す対象)。
WRITE_OPERATIONS = (
    REPORT_LAST_SEEN,
    REGISTER_DOCUMENTS,
    DISCARD_DELETIONS,
    DELETE_DOCUMENTS,
    DELETE_DELETION_RECORDS,
)


@dataclass(frozen=True)
class RecordedCall:
    operation: str
    arguments: dict[str, Any]


@dataclass
class _StartedCrawl:
    source_id: str
    payload: dict[str, Any]
    finish_digest: tuple[Any, ...] | None


def _finish_digest(payload: dict[str, Any]) -> tuple[Any, ...]:
    """実 Indexer の終了通知のダイジェスト。

    `outcome`・件数・重複を除いた ID 一覧が対象で、`finished_at` は除く。
    省略(None)と空の一覧は別の値として扱う。
    """

    def normalized(name: str) -> tuple[str, ...] | None:
        ids = payload.get(name)
        return None if ids is None else tuple(sorted(set(ids)))

    return (
        payload["outcome"],
        payload.get("enumerated_count"),
        normalized("skipped_document_ids"),
        normalized("oversize_document_ids"),
    )


class FakeIndexerClient(IndexerClient):
    def __init__(self) -> None:
        self.behavior = FakeBehavior()
        self.registration_failures: dict[str, FailureType] = {}
        self._lock = threading.Lock()
        self._calls: list[RecordedCall] = []
        self._started: dict[str, _StartedCrawl] = {}
        self._finished: dict[str, FinishOutcome] = {}

    # --- 呼び出しの記録 ---

    @property
    def calls(self) -> list[RecordedCall]:
        with self._lock:
            return list(self._calls)

    def operations(self) -> list[str]:
        return [call.operation for call in self.calls]

    def calls_of(self, *operations: str) -> list[RecordedCall]:
        return [call for call in self.calls if call.operation in operations]

    # --- IndexerClient ---

    def start_crawl(
        self,
        *,
        crawl_id: str,
        source_id: str,
        crawl_started_at: datetime,
        ttl: int,
        ratio_threshold: float,
        min_delete_count: int,
        force_delete: bool,
        rewrite_mode: bool,
    ) -> StartReply:
        payload = payloads.start_payload(
            crawl_id=crawl_id,
            source_id=source_id,
            crawl_started_at=crawl_started_at,
            ttl=ttl,
            ratio_threshold=ratio_threshold,
            min_delete_count=min_delete_count,
            force_delete=force_delete,
            rewrite_mode=rewrite_mode,
        )
        self._record(
            START_CRAWL,
            crawl_id=crawl_id,
            source_id=source_id,
            crawl_started_at=crawl_started_at,
            ttl=ttl,
            ratio_threshold=ratio_threshold,
            min_delete_count=min_delete_count,
            force_delete=force_delete,
            rewrite_mode=rewrite_mode,
        )
        if (intercepted := self.behavior.enter(START_CRAWL, crawl_id)) is not None:
            return intercepted.value
        return self._accept_start(crawl_id, source_id, payload)

    def report_last_seen(
        self,
        source_id: str,
        *,
        crawl_id: str,
        crawl_started_at: datetime,
        lock: LockInfo,
        document_ids: Sequence[str],
    ) -> LastSeenReply:
        payloads.last_seen_payload(
            crawl_id=crawl_id,
            crawl_started_at=crawl_started_at,
            lock=lock,
            document_ids=document_ids,
        )
        self._record(
            REPORT_LAST_SEEN,
            source_id=source_id,
            crawl_id=crawl_id,
            crawl_started_at=crawl_started_at,
            lock=lock,
            document_ids=list(document_ids),
        )
        if (intercepted := self.behavior.enter(REPORT_LAST_SEEN, source_id)) is not None:
            return intercepted.value
        if (
            rejected := self._admission_rejection(crawl_id, source_id, crawl_started_at)
        ) is not None:
            return rejected
        return LastSeenResults(
            entries=tuple(LastSeenEntry(i, LastSeenResult.UPDATED) for i in document_ids)
        )

    def register_documents(
        self,
        source_id: str,
        *,
        crawl_id: str,
        crawl_started_at: datetime,
        lock: LockInfo,
        documents: Sequence[DocumentToRegister],
    ) -> BatchReply:
        payloads.batch_payload(
            crawl_id=crawl_id, crawl_started_at=crawl_started_at, lock=lock, documents=documents
        )
        self._record(
            REGISTER_DOCUMENTS,
            source_id=source_id,
            crawl_id=crawl_id,
            crawl_started_at=crawl_started_at,
            lock=lock,
            documents=list(documents),
        )
        if (intercepted := self.behavior.enter(REGISTER_DOCUMENTS, source_id)) is not None:
            return intercepted.value
        if (
            rejected := self._admission_rejection(crawl_id, source_id, crawl_started_at)
        ) is not None:
            return rejected
        return BatchResults(
            documents=tuple(self._document_result(source_id, document) for document in documents)
        )

    def finish_crawl(
        self,
        crawl_id: str,
        *,
        source_id: str,
        outcome: FinishOutcome,
        finished_at: datetime,
        enumerated_count: int | None = None,
        skipped_document_ids: Sequence[str] | None = None,
        oversize_document_ids: Sequence[str] | None = None,
    ) -> FinishReply:
        payload = payloads.finish_payload(
            source_id=source_id,
            outcome=outcome,
            finished_at=finished_at,
            enumerated_count=enumerated_count,
            skipped_document_ids=skipped_document_ids,
            oversize_document_ids=oversize_document_ids,
        )
        self._record(
            FINISH_CRAWL,
            crawl_id=crawl_id,
            source_id=source_id,
            outcome=outcome,
            finished_at=finished_at,
            enumerated_count=enumerated_count,
            skipped_document_ids=None
            if skipped_document_ids is None
            else list(skipped_document_ids),
            oversize_document_ids=(
                None if oversize_document_ids is None else list(oversize_document_ids)
            ),
        )
        if (intercepted := self.behavior.enter(FINISH_CRAWL, crawl_id)) is not None:
            return intercepted.value
        return self._accept_finish(crawl_id, source_id, outcome, payload)

    def get_crawl_status(self, crawl_id: str) -> StatusReply:
        self._record(GET_CRAWL_STATUS, crawl_id=crawl_id)
        if (intercepted := self.behavior.enter(GET_CRAWL_STATUS, crawl_id)) is not None:
            return intercepted.value
        return self._status_of(crawl_id)

    def discard_deletions(self, source_id: str, *, lock: LockInfo) -> DiscardReply:
        self._record(DISCARD_DELETIONS, source_id=source_id, lock=lock)
        if (intercepted := self.behavior.enter(DISCARD_DELETIONS, source_id)) is not None:
            return intercepted.value
        return DiscardResult(discarded_crawl_ids=())

    def delete_documents(self, source_id: str, *, lock: LockInfo) -> DeleteDocumentsReply:
        self._record(DELETE_DOCUMENTS, source_id=source_id, lock=lock)
        if (intercepted := self.behavior.enter(DELETE_DOCUMENTS, source_id)) is not None:
            return intercepted.value
        return DocumentsDeleted(deleted_count=0)

    def delete_deletion_records(self, source_id: str, *, lock: LockInfo) -> DeleteRecordsReply:
        self._record(DELETE_DELETION_RECORDS, source_id=source_id, lock=lock)
        if (intercepted := self.behavior.enter(DELETE_DELETION_RECORDS, source_id)) is not None:
            return intercepted.value
        return DeletionRecordsDeleted(deleted=True)

    # --- 内部 ---

    def _accept_start(self, crawl_id: str, source_id: str, payload: dict[str, Any]) -> StartReply:
        started = self._started.get(crawl_id)
        if started is None:
            self._started[crawl_id] = _StartedCrawl(source_id, payload, finish_digest=None)
            return Succeeded()
        if crawl_id in self._finished:
            return IndexerRejected(409, "crawl_already_finished")
        if started.payload != payload:
            return IndexerRejected(409, "crawl_start_conflict")
        return Succeeded()

    def _admission_rejection(
        self, crawl_id: str, source_id: str, crawl_started_at: datetime
    ) -> IndexerRejected | None:
        """`last-seen`・バッチ登録の受理条件(実 Indexer の `AdmissionChecker`。arch 9.5)。

        開始通知を受けていない・ソースまたは `crawl_started_at` の不一致・終了通知の受理後は、
        リクエスト全体の 409 になる。判定の順は実 Indexer と同じ。
        """
        started = self._started.get(crawl_id)
        if started is None:
            return IndexerRejected(409, "crawl_not_started")
        if started.source_id != source_id:
            return IndexerRejected(409, "crawl_source_mismatch")
        if started.payload["crawl_started_at"] != format_instant(crawl_started_at):
            return IndexerRejected(409, "crawl_started_at_mismatch")
        outcome = self._finished.get(crawl_id)
        if outcome is None:
            return None
        # `failed`・`cancelled` の終了通知は状態を終端にし(`crawl_already_closed`)、
        # `enumeration_completed` は `finish_received_at` を記録する(`crawl_finished`)。
        if outcome is FinishOutcome.ENUMERATION_COMPLETED:
            return IndexerRejected(409, "crawl_finished")
        return IndexerRejected(409, "crawl_already_closed")

    def _accept_finish(
        self, crawl_id: str, source_id: str, outcome: FinishOutcome, payload: dict[str, Any]
    ) -> FinishReply:
        started = self._started.get(crawl_id)
        if started is None:
            return Succeeded()  # 未知の `crawl_id` は、実 Indexer も 202 で破棄する(何も記録しない)
        if started.source_id != source_id:
            return IndexerRejected(409, "finish_source_mismatch")
        digest = _finish_digest(payload)
        if started.finish_digest is None:
            started.finish_digest = digest
            self._finished[crawl_id] = outcome
        elif started.finish_digest != digest:
            return IndexerRejected(409, "finish_content_mismatch")
        return Succeeded()

    def _status_of(self, crawl_id: str) -> StatusReply:
        started = self._started.get(crawl_id)
        if started is None:
            return IndexerRejected(404, "crawl_not_found")
        outcome = self._finished.get(crawl_id)
        if outcome is None:
            return CrawlStatus(crawl_id, started.source_id, "running")
        if outcome == FinishOutcome.ENUMERATION_COMPLETED:
            return CrawlStatus(crawl_id, started.source_id, "deleted")
        return CrawlStatus(crawl_id, started.source_id, "failed", reason=f"outcome_{outcome.value}")

    def _record(self, operation: str, **arguments: Any) -> None:
        with self._lock:
            self._calls.append(RecordedCall(operation, arguments))

    def _document_result(
        self, source_id: str, document: DocumentToRegister
    ) -> DocumentRegistered | DocumentFailed:
        document_id = hashlib.sha256(f"{source_id}\0{document.external_id}".encode()).hexdigest()
        failure_type = self.registration_failures.get(document.external_id)
        if failure_type is not None:
            return DocumentFailed(document.external_id, document_id, failure_type)
        return DocumentRegistered(
            document.external_id, document_id, Change.CREATED, extract_failed=False
        )
