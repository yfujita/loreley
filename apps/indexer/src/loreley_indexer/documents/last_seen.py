"""`last_seen_at` の部分更新(`last-seen`)のドメイン処理(arch 5章、api 4.2)。

Crawler が列挙で見つけた文書について、取得より前に `last_seen_at` だけを max 比較で更新する。
取得・抽出・登録が失敗しても更新済みのまま残るので、スキップした文書が期限で誤削除されない。
`rewrite_mode` は使わない。max 比較はアダプタ(`raise_last_seen_at`)が行う。

OpenSearch の全体異常(`UnavailableError`)は伝播させる(api 層が 503)。
"""

import re
from collections.abc import Sequence

from loreley_indexer.common.clock import Clock
from loreley_indexer.common.source_locks import SourceLocks
from loreley_indexer.crawl_runs import AdmissionChecker
from loreley_indexer.documents.config import RegistrationConfig
from loreley_indexer.documents.ownership import LockOwnershipChecker
from loreley_indexer.documents.requests import CrawlContext
from loreley_indexer.documents.results import LastSeenEntry, LastSeenResult
from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    JobsReader,
    NotFound,
    OpenSearchUnexpectedResponseError,
    Rejected,
    SearchIndexRepository,
    Unchanged,
    Updated,
)

_DOCUMENT_ID_PATTERN = re.compile(r"[0-9a-f]{64}")


class LastSeenUpdater:
    def __init__(
        self,
        *,
        config: RegistrationConfig,
        admission_checker: AdmissionChecker,
        search_index: SearchIndexRepository,
        jobs: JobsReader,
        source_locks: SourceLocks,
        clock: Clock,
    ) -> None:
        self._config = config
        self._admission_checker = admission_checker
        self._search_index = search_index
        self._ownership = LockOwnershipChecker(jobs, clock)
        self._source_locks = source_locks

    def update(self, context: CrawlContext, document_ids: Sequence[str]) -> list[LastSeenEntry]:
        """文書ごとの結果を、入力と同じ順で返す。

        件数の上限超過と、64 桁の小文字 16 進でない ID は ValueError(api 層が 400 にする。
        防御的な検査で、入力値は例外に含めない)。
        受理条件を満たさなければ `AdmissionRejectedError` を送出する(1 件も書かない)。
        """
        self._validate(document_ids)
        with self._source_locks.hold(context.source_id):
            self._admission_checker.check(
                source_id=context.source_id,
                crawl_id=context.crawl_id,
                crawl_started_at=context.crawl_started_at,
            )
            return self._update_all(context, document_ids)

    def _validate(self, document_ids: Sequence[str]) -> None:
        if len(document_ids) > self._config.max_last_seen_ids:
            raise ValueError("too many document_ids")
        if not all(_DOCUMENT_ID_PATTERN.fullmatch(document_id) for document_id in document_ids):
            raise ValueError("document_id must be 64 lowercase hex characters")

    def _update_all(
        self, context: CrawlContext, document_ids: Sequence[str]
    ) -> list[LastSeenEntry]:
        entries: list[LastSeenEntry] = []
        lock_lost = False
        for document_id in document_ids:
            # 最初の失敗以降は、未処理の文書も書かずに `lock_not_owned` にする(plan 案5)。
            lock_lost = lock_lost or not self._ownership.is_owned(context)
            result = (
                LastSeenResult.LOCK_NOT_OWNED
                if lock_lost
                else self._raise_last_seen_at(context, document_id)
            )
            entries.append(LastSeenEntry(document_id, result))
        return entries

    def _raise_last_seen_at(self, context: CrawlContext, document_id: str) -> LastSeenResult:
        match self._search_index.raise_last_seen_at(document_id, context.crawl_started_at):
            case Updated():
                return LastSeenResult.UPDATED
            case Unchanged():
                return LastSeenResult.UNCHANGED
            case NotFound():
                return LastSeenResult.NOT_FOUND
            case Conflict():
                # `retry_on_conflict` を超えた 409。再試行可能な文書単位の失敗(K51)。
                return LastSeenResult.UPDATE_CONFLICT
            case Rejected(error_type=error_type):
                # 固定のスクリプトの Update が拒否されるのは、文書ではなく Indexer 側の異常。
                raise OpenSearchUnexpectedResponseError(error_type)
