"""削除結果 1 件の処理: 先行待ち → メンテナンスフラグ → 判定 → 実行(arch 9.7)。

書き込みはすべて、自分の結果を読んだ版を条件にした更新で行う。読み直して終端状態(ソース削除の
`discarded` など)・404 なら、何も書かずに止まる(`CLOSED`)。世代は確認しない。新しい開始通知が
来ても、受理済みの旧い削除は止まらない(9.7、9.12)。

OpenSearch の全体異常などの例外は、結果を変えずに伝播する(ワーカーが ID と例外クラス名だけを
ログに出し、次の走査で処理し直す)。文書の削除のエラーだけは、実行の中で有界リトライし、
直らなければ `failed`(`delete_error`)にする(`BatchExecutor`)。
"""

from dataclasses import replace

from loreley_indexer.common.clock import Clock
from loreley_indexer.crawl_runs.deletion.executor import BatchExecutor
from loreley_indexer.crawl_runs.deletion.judge import DeletionJudge, Execution
from loreley_indexer.crawl_runs.deletion.judgment import progress_update
from loreley_indexer.crawl_runs.deletion.outcome import DeletionOutcome
from loreley_indexer.crawl_runs.deletion.result_writer import (
    ResultClosed,
    ResultWriter,
    TerminalTransition,
)
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionResults,
    DeletionStatus,
    StoredResult,
)
from loreley_indexer.infrastructure.opensearch import JobsReader


class DeletionProcessor:
    def __init__(
        self,
        *,
        results: DeletionResults,
        jobs: JobsReader,
        clock: Clock,
        writer: ResultWriter,
        judge: DeletionJudge,
        executor: BatchExecutor,
    ) -> None:
        self._results = results
        self._jobs = jobs
        self._clock = clock
        self._writer = writer
        self._judge = judge
        self._executor = executor

    def process(self, crawl_id: str) -> DeletionOutcome:
        try:
            return self._process(crawl_id)
        except ResultClosed:
            return DeletionOutcome.CLOSED

    def _process(self, crawl_id: str) -> DeletionOutcome:
        current = self._results.fetch_result(crawl_id)
        if current is None or current.record.status.is_terminal:
            return DeletionOutcome.CLOSED
        if current.record.finish_received_at is None:
            return DeletionOutcome.NOT_QUEUED
        # 順1: 先行する削除が終端状態になるまで待つ。待機中は判定せず、何も書かない。
        if self._results.preceding_results(current.record):
            return DeletionOutcome.WAITING
        # 順2: 判定の前に、メンテナンスフラグを確認する(待機していたものも、順番が来た時点で)。
        if self._jobs.is_maintenance_enabled():
            self._writer.finish(
                current,
                TerminalTransition(DeletionStatus.FAILED, DeletionReason.MAINTENANCE),
            )
            return DeletionOutcome.FINISHED

        current = self._mark_judging(current)
        verdict = self._judge.judge(current.record)
        if isinstance(verdict, Execution):
            return self._executor.execute(current, verdict.targets, verdict.measurements)
        self._writer.finish(
            current,
            verdict.transition,
            progress_update(verdict.measurements, verdict.deleted_count),
        )
        return DeletionOutcome.FINISHED

    def _mark_judging(self, current: StoredResult) -> StoredResult:
        """待機から判定への遷移で `deletion_started_at` を書く(条件付き更新。案)。"""
        if current.record.deletion_started_at is not None:
            return current
        started_at = self._clock.now()
        return self._writer.advance(
            current, lambda record: replace(record, deletion_started_at=started_at)
        )
