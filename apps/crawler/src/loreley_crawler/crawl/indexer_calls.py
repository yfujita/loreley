"""Indexer への呼び出し: リトライ・確認点・失敗の対応づけ(architecture 6.1・6.2・7.8)。

`indexer_client` の型付きの結果を、`crawl` の扱いにする。
- `IndexerUnavailable`(500・503・接続エラー・タイムアウト): リトライし、直らなければ
  `CrawlFailure`(`indexer_unavailable`。スキップにしない)
- `IndexerRejected`(400・409・404・405・その他、契約外の応答): リトライせず `CrawlFailure`
  (`indexer_rejected`)
- 文書単位の `lock_not_owned`: `JobContext` に喪失として記録し、`OwnershipLost`
- 終了通知(`finish_crawl`)だけは、リトライを尽くした `IndexerUnavailable` と 409(内容・ソースの
  不一致)を `finish_notice_failed` にする(4.8・7.8)。確認点も、取り消しだけ(終了通知は所有確認の
  対象外。architecture 5.7)

どの要請も、各試行の前に確認点(所有・取り消し・メンテナンス)を通す(R8)。送る値は、
`SettingsSnapshot` と `LockInfo` から毎回同じものを組み立てる(再送は同一値。7.4)。
本文・Indexer のエラーメッセージ・リクエストの値は、説明にもログにも出さない(R11)。
"""

from collections.abc import Callable, Sequence
from itertools import batched
from typing import NoReturn

from loreley_crawler.crawl.failure import CrawlFailure
from loreley_crawler.crawl.finish_notice import FinishNotice
from loreley_crawler.crawl.snapshot import SettingsSnapshot
from loreley_crawler.infrastructure.indexer_client import (
    BatchResults,
    DocumentToRegister,
    IndexerClient,
    IndexerRejected,
    IndexerUnavailable,
    LastSeenResult,
    LastSeenResults,
    LockInfo,
    StatusReply,
)
from loreley_crawler.jobs import (
    LOSS_LOCK_NOT_OWNED,
    Check,
    FailureReason,
    JobContext,
    OwnershipLost,
)


class IndexerCaller:
    def __init__(
        self,
        *,
        context: JobContext,
        client: IndexerClient,
        source_id: str,
        lock: LockInfo,
        snapshot: SettingsSnapshot,
        last_seen_max_ids: int,
    ) -> None:
        self._context = context
        self._client = client
        self._source_id = source_id
        self._lock = lock
        self._snapshot = snapshot
        self._last_seen_max_ids = last_seen_max_ids

    @property
    def max_attempts(self) -> int:
        """リクエスト単位・文書単位の最大試行回数(最初の 1 回を含む。architecture 6.1)。"""
        return self._context.retrier().policy.max_attempts

    def start_crawl(self) -> None:
        """開始通知。再送でも、スナップショットから同じ値を送る。"""
        snapshot = self._snapshot
        self._call(
            lambda: self._client.start_crawl(
                crawl_id=self._context.job_id,
                source_id=self._source_id,
                crawl_started_at=snapshot.crawl_started_at,
                ttl=snapshot.ttl,
                ratio_threshold=snapshot.ratio_threshold,
                min_delete_count=snapshot.min_delete_count,
                force_delete=snapshot.force_delete,
                rewrite_mode=snapshot.rewrite_mode,
            )
        )

    def report_last_seen(self, document_ids: Sequence[str]) -> None:
        """`last-seen` を要請する。上限以下に分割する。`update_conflict` は上限付きでリトライ。"""
        for ids in batched(document_ids, self._last_seen_max_ids):
            self._report_last_seen_of(list(ids))

    def register_documents(self, documents: Sequence[DocumentToRegister]) -> BatchResults:
        """バッチ登録(1 回の要請。リクエスト全体の失敗のリトライを含む)。文書単位の結果を返す。"""
        snapshot = self._snapshot
        return self._call(
            lambda: self._client.register_documents(
                self._source_id,
                crawl_id=self._context.job_id,
                crawl_started_at=snapshot.crawl_started_at,
                lock=self._lock,
                documents=documents,
            )
        )

    def finish_crawl(self, notice: FinishNotice, *, checks: Check) -> None:
        """終了通知。`notice` の内容をそのまま送る(再送でも同一。202 は受理の確認ではない)。"""
        self._call(
            lambda: self._client.finish_crawl(
                self._context.job_id,
                source_id=self._source_id,
                outcome=notice.outcome,
                finished_at=notice.finished_at,
                enumerated_count=notice.enumerated_count,
                skipped_document_ids=notice.skipped_document_ids,
                oversize_document_ids=notice.oversize_document_ids,
            ),
            checks=checks,
            exhausted_reason=FailureReason.FINISH_NOTICE_FAILED,
            conflict_reason=FailureReason.FINISH_NOTICE_FAILED,
        )

    def get_status(self) -> StatusReply:
        """Status API を 1 回呼ぶ(リトライしない。失敗の連続は `StatusPoller` が数える)。"""
        return self._client.get_crawl_status(self._context.job_id)

    def wait_before_resend(self, round_number: int) -> None:
        """文書単位の再送の前に、リトライと同じバックオフで待つ(待ちの途中で確認点を通す)。"""
        retrier = self._context.retrier()
        self._context.wait(retrier.policy.backoff_seconds(round_number, retrier.random_source))

    def raise_lock_lost(self) -> NoReturn:
        """文書単位の `lock_not_owned` を、所有権の喪失として記録して知らせる(5.7)。"""
        self._context.record_lock_not_owned()
        raise OwnershipLost(LOSS_LOCK_NOT_OWNED)

    def _report_last_seen_of(self, document_ids: list[str]) -> None:
        pending_ids = document_ids
        for attempt in range(1, self.max_attempts + 1):
            pending_ids = self._conflicting_ids(self._report_once(pending_ids))
            if not pending_ids:
                return
            if attempt < self.max_attempts:
                self.wait_before_resend(attempt)
        raise CrawlFailure(
            FailureReason.CONFLICT_UNRESOLVED,
            f"update_conflict が解消しない({len(pending_ids)} 件)",
        )

    def _report_once(self, document_ids: list[str]) -> LastSeenResults:
        return self._call(
            lambda: self._client.report_last_seen(
                self._source_id,
                crawl_id=self._context.job_id,
                crawl_started_at=self._snapshot.crawl_started_at,
                lock=self._lock,
                document_ids=document_ids,
            )
        )

    def _conflicting_ids(self, results: LastSeenResults) -> list[str]:
        if any(entry.result is LastSeenResult.LOCK_NOT_OWNED for entry in results.entries):
            self.raise_lock_lost()
        return [
            entry.document_id
            for entry in results.entries
            if entry.result is LastSeenResult.UPDATE_CONFLICT
        ]

    def _call[T](
        self,
        operation: Callable[[], T | IndexerUnavailable | IndexerRejected],
        *,
        checks: Check = Check.ALL,
        exhausted_reason: FailureReason = FailureReason.INDEXER_UNAVAILABLE,
        conflict_reason: FailureReason = FailureReason.INDEXER_REJECTED,
    ) -> T:
        """リトライを尽くした `IndexerUnavailable` は `exhausted_reason`、409 は `conflict_reason`、
        そのほかの拒否は `indexer_rejected` の `CrawlFailure` にする。"""
        reply = self._context.retrier(checks).run(
            operation, is_retryable_result=lambda reply: isinstance(reply, IndexerUnavailable)
        )
        if isinstance(reply, IndexerUnavailable):
            raise CrawlFailure(exhausted_reason, f"Indexer が応答しない({reply.reason})")
        if isinstance(reply, IndexerRejected):
            reason = conflict_reason if reply.status_code == 409 else FailureReason.INDEXER_REJECTED
            raise CrawlFailure(
                reason, f"Indexer が要請を拒否した(HTTP {reply.status_code}、{reply.error_code})"
            )
        return reply
