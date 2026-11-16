"""Indexer の HTTP API を呼ぶクライアントのインターフェース(module 4.9)。

1 つの API につき 1 つの操作。呼び出しは同期で、呼んだスレッドの中で完結する(Job Runner の
スレッドだけが呼ぶ。R9)。どの操作も、成功の型・`IndexerUnavailable`・`IndexerRejected` のどれかを
返し、例外にしない(`results.py`)。

持たないもの: リトライとバックオフ(`common` の汎用機構を `JobContext` が束ねる)、確認点(所有・
取り消し・メンテナンス)、エラー別のジョブの扱い(`crawl`・`source_delete`。architecture 7.8)、
ID の算出と検証。

実装: `HttpIndexerClient`(本番)と、テスト用の偽物(`tests/fakes/fake_indexer_client.py`)。
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime

from loreley_crawler.infrastructure.indexer_client.models import (
    DocumentToRegister,
    FinishOutcome,
    LockInfo,
)
from loreley_crawler.infrastructure.indexer_client.results import (
    BatchReply,
    DeleteDocumentsReply,
    DeleteRecordsReply,
    DiscardReply,
    FinishReply,
    LastSeenReply,
    StartReply,
    StatusReply,
)


class IndexerClient(ABC):
    @abstractmethod
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
        """開始通知(`POST /crawls/start`)。再送では、保存済みの同一の値を渡すこと。"""

    @abstractmethod
    def report_last_seen(
        self,
        source_id: str,
        *,
        crawl_id: str,
        crawl_started_at: datetime,
        lock: LockInfo,
        document_ids: Sequence[str],
    ) -> LastSeenReply:
        """`last-seen`(`POST /sources/{source_id}/last-seen`)。取得より前に要請する。"""

    @abstractmethod
    def register_documents(
        self,
        source_id: str,
        *,
        crawl_id: str,
        crawl_started_at: datetime,
        lock: LockInfo,
        documents: Sequence[DocumentToRegister],
    ) -> BatchReply:
        """バッチ登録(`POST /sources/{source_id}/documents:batch`)。文書ごとの結果を返す。"""

    @abstractmethod
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
        """終了通知(`POST /crawls/{crawl_id}/finish`)。再送では、固定した内容を渡すこと。"""

    @abstractmethod
    def get_crawl_status(self, crawl_id: str) -> StatusReply:
        """Status API(`GET /crawls/{crawl_id}`)。削除結果を読む。"""

    @abstractmethod
    def discard_deletions(self, source_id: str, *, lock: LockInfo) -> DiscardReply:
        """ソース削除 1(`POST /sources/{source_id}/deletions:discard`)。所有は確認されない。"""

    @abstractmethod
    def delete_documents(self, source_id: str, *, lock: LockInfo) -> DeleteDocumentsReply:
        """ソース削除 2(`DELETE /sources/{source_id}/documents`)。`lock` を JSON ボディで送る。"""

    @abstractmethod
    def delete_deletion_records(self, source_id: str, *, lock: LockInfo) -> DeleteRecordsReply:
        """ソース削除 3(`DELETE /sources/{source_id}/deletion-records`)。ボディは 2 と同じ。"""
