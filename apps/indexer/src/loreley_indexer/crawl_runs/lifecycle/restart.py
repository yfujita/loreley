"""起動時の整理(arch 9.8、案 3。M-12、U-20)。

終了通知を受理済みで終端状態でない削除結果(待機中・判定中・実行中)を `failed`
(`indexer_restart`)にする。再開せず、待機中も実行しない。保存した ID 一覧は、終端状態へ遷移する
書き込みと同じ書き込みで消える(K35)。終了通知が届いていない `running` には触れない
(次の開始通知で `superseded` になる)。

`main.py` が HTTP の受け付けを始める前に呼ぶ(受け付け後だと、新しい終了通知を誤って
`failed` にしうる。M-12)。受け付け前なので、ソース単位の直列処理は使わない。
"""

import logging
from dataclasses import replace

from loreley_indexer.crawl_runs.lifecycle.config import LifecycleConfig
from loreley_indexer.crawl_runs.lifecycle.records import DeletionReason, DeletionStatus
from loreley_indexer.crawl_runs.lifecycle.results import DeletionResults, retry_after_conflict
from loreley_indexer.infrastructure.opensearch import Conflict, Written
from loreley_indexer.infrastructure.opensearch.store import LIST_MAX_SIZE

logger = logging.getLogger(__name__)


class RestartCleaner:
    def __init__(self, *, config: LifecycleConfig, results: DeletionResults) -> None:
        self._config = config
        self._results = results

    def fail_unfinished_results(self) -> int:
        """`failed`(`indexer_restart`)にした件数を返す。"""
        failed_count = 0
        while True:
            unfinished = self._results.list_unfinished_received()
            failed_count += sum(self._fail(record.crawl_id) for record in unfinished)
            # 一覧の上限に達していたら、まだ残りがありうるので繰り返す。
            if len(unfinished) < LIST_MAX_SIZE:
                break
        if failed_count:
            logger.info(
                "unfinished deletion results were failed on restart: count=%d", failed_count
            )
        return failed_count

    def _fail(self, crawl_id: str) -> bool:
        def attempt() -> bool | Conflict:
            current = self._results.fetch_result(crawl_id)
            # 読み直したら、終端状態になった・消えた場合は何もしない。
            if current is None or current.record.status.is_terminal:
                return False
            # `deleted_count` が未記録なら、削除は 1 件も実行されていない(進捗は各バッチの前に
            # 書かれる)ので 0 とする(D-93)。記録済みの件数は減らさない。
            outcome = self._results.transition_to_terminal(
                current,
                DeletionStatus.FAILED,
                reason=DeletionReason.INDEXER_RESTART,
                progress=replace(current.record, deleted_count=current.record.deleted_count or 0),
            )
            # 409 も文書なしも読み直す(消えていれば次の確認で何もしない)。
            return True if isinstance(outcome, Written) else Conflict()

        return retry_after_conflict(attempt, max_rereads=self._config.write_conflict_max_rereads)
