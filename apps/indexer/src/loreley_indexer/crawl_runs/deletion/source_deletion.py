"""ソース削除 1〜3(arch 9.14 の手順 1・2・4、api 4.6〜4.8。案 8)。

呼び出し元は Crawler のソース削除ジョブ。1〜3 の順に呼ぶ。どれも何度でも再実行できる(冪等)。
Indexer の手順の正しさは、ロックの有無に依存しない。

1. `discard_source_crawls`: そのソースの終端状態でない削除結果をすべて `discarded`
   (`source_deleted`)にする。`lock` は受け取るが確認しない(応答待ちでリースが切れうるため。
   再実行を妨げない。案 8)。実行中の削除バッチの完了後、次のバッチの前確認より前に書く。
2. `delete_source_documents`: `source_id` の文書を `delete_by_query` で消し切る。
3. `delete_source_records`: `deletion-{source_id}` と該当する結果を消す。

2・3 は `lock` を必須とし、所有を確認できなければ、何も書かずに `LockNotOwnedError`(409)。
"""

from loreley_indexer.common.clock import Clock
from loreley_indexer.common.errors import LockNotOwnedError, UnavailableError
from loreley_indexer.common.locks import LockInfo, is_lock_owned
from loreley_indexer.crawl_runs.deletion.config import DeletionConfig
from loreley_indexer.crawl_runs.deletion.exclusion import SourceBatchExclusion
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionResultRecord,
    DeletionResults,
    DeletionStatus,
)
from loreley_indexer.infrastructure.opensearch import (
    DocumentFilter,
    JobsReader,
    SearchIndexRepository,
    Written,
)


class SourceDeletion:
    def __init__(
        self,
        *,
        config: DeletionConfig,
        results: DeletionResults,
        search_index: SearchIndexRepository,
        jobs: JobsReader,
        clock: Clock,
        exclusion: SourceBatchExclusion,
    ) -> None:
        self._config = config
        self._results = results
        self._search_index = search_index
        self._jobs = jobs
        self._clock = clock
        self._exclusion = exclusion

    def discard_source_crawls(self, source_id: str, lock: LockInfo) -> list[str]:
        """終端状態でない削除結果を、待機中も含めてすべて `discarded` にし、その `crawl_id` を返す。

        `lock` は確認しない(案 8)。書き込みは読んだ版を条件にした更新で、すでに終端状態の
        結果は上書きしない。409・文書なしは読み直して再試行し、`discard_max_attempts` を超えたら
        `UnavailableError`(再実行で続きから完了する)。応答の時点で、そのソースの削除バッチは
        動いていない(排他。9.14、P29)。
        """
        discarded_crawl_ids: list[str] = []
        with self._exclusion.hold_priority(source_id):
            rounds = 0
            while True:
                remaining = self._results.list_non_terminal(source_id)
                if not remaining:
                    return discarded_crawl_ids
                if rounds == self._config.discard_max_attempts:
                    raise UnavailableError("discard_conflict")
                discarded_crawl_ids += self._discard_each(remaining)
                rounds += 1

    def _discard_each(self, remaining: list[DeletionResultRecord]) -> list[str]:
        discarded: list[str] = []
        for record in remaining:
            current = self._results.fetch_result(record.crawl_id)
            # 読み直して、終端状態になった・消えた結果は対象外(上書きしない)。
            if current is None or current.record.status.is_terminal:
                continue
            outcome = self._results.transition_to_terminal(
                current, DeletionStatus.DISCARDED, reason=DeletionReason.SOURCE_DELETED
            )
            if isinstance(outcome, Written):
                discarded.append(record.crawl_id)
        return discarded

    def delete_source_documents(self, source_id: str, lock: LockInfo) -> int:
        """`source_id` の文書を消し切り、削除した件数を返す。

        `refresh` → `delete_by_query`(`conflicts=proceed`)→ `refresh` → `_count` を、`_count` が
        0 になるまで繰り返す。再実行は `delete_by_query_max_reruns` まで(最初の 1 回の後の回数)。
        上限まで 0 にならなければ、`UnavailableError`(再試行可能。Crawler がジョブを `failed` に
        し、再実行で残りを消す。K48)。競合した文書は、再登録されたものも含めて再実行で消える。
        ロックの所有は、実行(再実行を含む)の前ごとに確認する(別のジョブが取った後の再実行で、
        新しい登録を消さないため)。
        """
        document_filter = DocumentFilter(source_id=source_id)
        deleted_count = 0
        with self._exclusion.hold_priority(source_id):
            for _ in range(1 + self._config.delete_by_query_max_reruns):
                self._require_lock_owned(source_id, lock)
                # 直前の書き込みが検索に反映されていないと、`delete_by_query` の対象にならない。
                self._search_index.refresh()
                deleted_count += self._search_index.delete_by_query(document_filter).deleted
                self._search_index.refresh()
                if self._search_index.count(document_filter) == 0:
                    return deleted_count
        raise UnavailableError("documents_remaining")

    def delete_source_records(self, source_id: str, lock: LockInfo) -> bool:
        """削除の記録を消す。1 件でも消したら True、すでになければ False(成功)。"""
        self._require_lock_owned(source_id, lock)
        return self._results.delete_source_records(source_id)

    def _require_lock_owned(self, source_id: str, lock: LockInfo) -> None:
        owned = is_lock_owned(
            self._jobs.fetch_lock(source_id),
            owner=lock.owner,
            job_id=lock.job_id,
            now=self._clock.now(),
        )
        if not owned:
            raise LockNotOwnedError
