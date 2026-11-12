"""削除の実行(arch 9.8)。バッチごとの確認と、文書ごとの TTL 再確認つき条件付き削除。

バッチ 1 回分(自分の結果の確認 → メンテナンスフラグの確認 → 進捗の書き込み → 文書の削除)を
ソース削除と同じ排他の中で行う(`SourceBatchExclusion`)。新しい開始通知が来ても止めない
(世代は確認しない。9.7)。

文書ごとの流れ: ID で読み直す → 同じソースで TTL を満たすか(現在時刻で)再確認 → 読んだ版を
条件にした削除。409 は読み直して再判定し(`write_conflict_max_rereads` まで)、超えたら削除せず
次の期限による削除に委ねる。すでにない文書・再確認で外れた文書は `deleted_count` に数えない。

削除のエラー(全体異常・文書固有の拒否)は、リトライ設定の回数まで試し、直らなければ
`failed`(`delete_error`)で止める(4.4)。それまでの削除件数は記録する。
文書の内容は、ログにも例外にも出さない(R9)。
"""

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from loreley_indexer.common.clock import Clock
from loreley_indexer.common.errors import UnavailableError
from loreley_indexer.common.timestamps import parse_instant
from loreley_indexer.crawl_runs.deletion.config import DeletionConfig
from loreley_indexer.crawl_runs.deletion.exclusion import SourceBatchExclusion
from loreley_indexer.crawl_runs.deletion.judgment import (
    Measurements,
    is_expired,
    progress_update,
)
from loreley_indexer.crawl_runs.deletion.outcome import DeletionOutcome
from loreley_indexer.crawl_runs.deletion.result_writer import ResultWriter, TerminalTransition
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionResultRecord,
    DeletionStatus,
    StoredResult,
)
from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    Deleted,
    JobsReader,
    NotFound,
    Rejected,
    SearchIndexRepository,
)

Jitter = Callable[[float], float]


def default_jitter(delay_seconds: float) -> float:
    """待ち時間を 0.5〜1 倍に散らす(再試行が同時に重ならないように)。上限は超えない。"""
    return delay_seconds * random.uniform(0.5, 1.0)


class _DeleteRejected(Exception):
    """削除が文書固有の拒否で終わった(OpenSearch のエラー種別名だけを持つ)。"""

    def __init__(self, error_type: str) -> None:
        super().__init__(error_type)
        self.error_type = error_type


class _DeleteFailed(Exception):
    """リトライ設定の回数まで試しても削除エラーが直らなかった。`detail` はエラーの種類だけ。"""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class _StopRequested(Exception):
    pass


@dataclass(frozen=True)
class _BatchResult:
    deleted_count: int
    failure_detail: str | None = None
    stop_requested: bool = False


class BatchExecutor:
    def __init__(
        self,
        *,
        config: DeletionConfig,
        search_index: SearchIndexRepository,
        jobs: JobsReader,
        clock: Clock,
        exclusion: SourceBatchExclusion,
        writer: ResultWriter,
        sleep: Callable[[float], object],
        jitter: Jitter = default_jitter,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> None:
        self._config = config
        self._search_index = search_index
        self._jobs = jobs
        self._clock = clock
        self._exclusion = exclusion
        self._writer = writer
        self._sleep = sleep
        self._jitter = jitter
        self._should_stop = should_stop

    def execute(
        self, current: StoredResult, targets: Sequence[str], measurements: Measurements
    ) -> DeletionOutcome:
        """`targets`(空でない)をバッチごとに処理し、終端状態を書く。

        `current` は判定を終えた時点の自分の結果。`ResultClosed`(自分の結果が終端状態・404)は
        呼び出し側へ伝播する(書き換えずに止まる)。
        """
        crawl_id = current.record.crawl_id
        source_id = current.record.source_id
        # 再実行(書き込みの失敗後など)でも、記録済みの件数から数え続ける(件数を減らさない)。
        deleted_count = current.record.deleted_count or 0
        for start in range(0, len(targets), self._config.batch_size):
            if self._should_stop():
                return DeletionOutcome.STOPPED
            batch = targets[start : start + self._config.batch_size]
            with self._exclusion.hold_batch(source_id):
                current = self._writer.reread(crawl_id)
                if self._jobs.is_maintenance_enabled():
                    self._finish(
                        current,
                        TerminalTransition(DeletionStatus.FAILED, DeletionReason.MAINTENANCE),
                        measurements,
                        deleted_count,
                    )
                    return DeletionOutcome.FINISHED
                current = self._writer.advance(
                    current, progress_update(measurements, deleted_count)
                )
                result = self._delete_batch(current.record, batch)
            deleted_count += result.deleted_count
            if result.stop_requested:
                return DeletionOutcome.STOPPED
            if result.failure_detail is not None:
                self._finish(
                    current,
                    TerminalTransition(
                        DeletionStatus.FAILED,
                        DeletionReason.DELETE_ERROR,
                        reason_detail=result.failure_detail,
                    ),
                    measurements,
                    deleted_count,
                )
                return DeletionOutcome.FINISHED
        self._finish(
            current, TerminalTransition(DeletionStatus.DELETED), measurements, deleted_count
        )
        return DeletionOutcome.FINISHED

    def _finish(
        self,
        current: StoredResult,
        transition: TerminalTransition,
        measurements: Measurements,
        deleted_count: int,
    ) -> None:
        self._writer.finish(current, transition, progress_update(measurements, deleted_count))

    def _delete_batch(self, record: DeletionResultRecord, batch: Sequence[str]) -> _BatchResult:
        deleted_count = 0
        for document_id in batch:
            try:
                was_deleted = self._delete_with_retry(record, document_id)
            except _DeleteFailed as failure:
                return _BatchResult(deleted_count, failure_detail=failure.detail)
            except _StopRequested:
                return _BatchResult(deleted_count, stop_requested=True)
            if was_deleted:
                deleted_count += 1
        return _BatchResult(deleted_count)

    def _delete_with_retry(self, record: DeletionResultRecord, document_id: str) -> bool:
        attempts = self._config.delete_error_retry_attempts
        detail = ""
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                self._sleep(self._backoff_seconds(attempt - 1))
                if self._should_stop():
                    raise _StopRequested
            try:
                return self._delete_one(record, document_id)
            except UnavailableError as error:
                detail = f"unavailable:{error.reason}"
            except _DeleteRejected as error:
                detail = f"rejected:{error.error_type}"
        raise _DeleteFailed(detail)

    def _delete_one(self, record: DeletionResultRecord, document_id: str) -> bool:
        """文書を削除したら True。すでにない・再確認で外れた・409 が上限を超えたときは False。"""
        for _ in range(1 + self._config.write_conflict_max_rereads):
            # 本文は読まない(再確認に要るのは `source_id` と `last_seen_at` だけ)。
            stored = self._search_index.fetch_for_deletion(document_id)
            if stored is None:
                return False  # すでにない(別の処理が削除した)
            if not self._is_still_deletable(record, stored.source):
                return False  # 更新された、または別のソースの文書
            outcome = self._search_index.delete_if_unchanged(
                document_id, seq_no=stored.seq_no, primary_term=stored.primary_term
            )
            match outcome:
                case Deleted():
                    return True
                case NotFound():
                    return False
                case Conflict():
                    continue  # 読み直して TTL を再判定する(D-87)
                case Rejected(error_type=error_type):
                    raise _DeleteRejected(error_type)
        return False  # 409 が読み直しの上限を超えた。次の期限による削除に委ねる(D-88)

    def _is_still_deletable(self, record: DeletionResultRecord, source: dict[str, Any]) -> bool:
        """同じソースの文書で、現在時刻で `last_seen_at + TTL < 現在時刻` を満たすか(9.8 (3))。

        読めない `last_seen_at` は期限切れとみなさない(削除しない側に倒す)。
        """
        if source.get("source_id") != record.source_id:
            return False
        last_seen_text = source.get("last_seen_at")
        if not isinstance(last_seen_text, str):
            return False
        try:
            last_seen_at = parse_instant(last_seen_text)
        except ValueError:
            return False
        return is_expired(last_seen_at, now=self._clock.now(), ttl_seconds=record.ttl)

    def _backoff_seconds(self, failed_attempts: int) -> float:
        delay = self._config.retry_backoff_initial_seconds * (
            self._config.retry_backoff_factor ** (failed_attempts - 1)
        )
        return self._jitter(min(delay, self._config.retry_backoff_max_seconds))
