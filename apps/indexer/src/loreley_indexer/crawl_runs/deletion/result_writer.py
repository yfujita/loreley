"""自分の削除結果の読み直しと、条件付きの書き込み(arch 9.7 順2〜6、9.8「ソース削除での停止」)。

書き込みはすべて `if_seq_no` の条件付き(`DeletionResults` が行う)。409・文書なしは読み直し、
自分の結果が終端状態(ソース削除の `discarded` など)・消えていたら、何も書かずに
`ResultClosed` で止まる。読み直しの回数は `write_conflict_max_rereads` までで、超えたら
`UnavailableError("write_conflict")`(結果は変えず、ワーカーの次の走査で処理し直す。R8)。
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from loreley_indexer.common.errors import UnavailableError
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionResultRecord,
    DeletionResults,
    DeletionStatus,
    StoredResult,
)
from loreley_indexer.infrastructure.opensearch import Written

logger = logging.getLogger(__name__)

RecordUpdate = Callable[[DeletionResultRecord], DeletionResultRecord]


class ResultClosed(Exception):
    """自分の削除結果が終端状態になった、または読めない(404)。書き換えずに止まる(9.8)。"""


@dataclass(frozen=True)
class TerminalTransition:
    status: DeletionStatus
    reason: DeletionReason | None = None
    reason_detail: str | None = None


class ResultWriter:
    def __init__(self, results: DeletionResults, *, max_rereads: int) -> None:
        self._results = results
        self._max_rereads = max_rereads

    def reread(self, crawl_id: str) -> StoredResult:
        """最新の自分の結果。終端状態・404 なら `ResultClosed`。"""
        current = self._results.fetch_result(crawl_id)
        if current is None or current.record.status.is_terminal:
            raise ResultClosed
        return current

    def advance(self, current: StoredResult, update: RecordUpdate) -> StoredResult:
        """終端でない更新(`deletion_started_at`、判定の数値、`deleted_count` の進捗)。

        `update` は、読み直した最新の記録に対して適用し直す(書き込みの間に変わった項目を消さない)。
        """
        for attempt in range(1 + self._max_rereads):
            if attempt > 0:
                current = self.reread(current.record.crawl_id)
            updated = update(current.record)
            outcome = self._results.replace_result(current, updated)
            if isinstance(outcome, Written):
                return StoredResult(
                    record=updated, seq_no=outcome.seq_no, primary_term=outcome.primary_term
                )
        raise UnavailableError("write_conflict")

    def finish(
        self,
        current: StoredResult,
        transition: TerminalTransition,
        update: RecordUpdate = lambda record: record,
    ) -> None:
        """終端状態へ遷移する。保存した ID 一覧は同じ書き込みで消える(`DeletionResults` が行う)。"""
        for attempt in range(1 + self._max_rereads):
            if attempt > 0:
                current = self.reread(current.record.crawl_id)
            outcome = self._results.transition_to_terminal(
                current,
                transition.status,
                reason=transition.reason,
                reason_detail=transition.reason_detail,
                progress=update(current.record),
            )
            if isinstance(outcome, Written):
                logger.info(
                    "deletion finished: crawl_id=%s status=%s reason=%s",
                    current.record.crawl_id,
                    transition.status.value,
                    transition.reason.value if transition.reason is not None else None,
                )
                return
        raise UnavailableError("write_conflict")
