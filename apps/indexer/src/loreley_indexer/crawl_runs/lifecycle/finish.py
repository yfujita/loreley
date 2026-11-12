"""終了通知の受理(arch 9.5、9.9、api 4.4。K25・K31・K32・K34・K35・K36・K38・K40)。

処理順(確定。K38): 形式の検証(400。`FinishNotification` の生成時) → `source_id` の照合
(409 `finish_source_mismatch`) → ダイジェストによる再送の判定 → 受理時の分岐。
受理の書き込みは、ソース単位の直列処理の中で、読んだ結果の版を条件にした更新で行う。
409 は読み直して最初から判定し直す(判定の根拠になる状態が変わりうるため)。
"""

import logging
from collections.abc import Callable
from dataclasses import replace
from enum import StrEnum

from loreley_indexer.common.clock import Clock
from loreley_indexer.common.errors import FinishContentMismatchError, FinishSourceMismatchError
from loreley_indexer.common.source_locks import SourceLocks
from loreley_indexer.crawl_runs.lifecycle.config import LifecycleConfig
from loreley_indexer.crawl_runs.lifecycle.notifications import FinishNotification
from loreley_indexer.crawl_runs.lifecycle.records import (
    DeletionReason,
    DeletionResultRecord,
    DeletionStatus,
    FinishOutcome,
)
from loreley_indexer.crawl_runs.lifecycle.results import (
    DeletionResults,
    StoredResult,
    retry_after_conflict,
)
from loreley_indexer.infrastructure.opensearch import Conflict, NotFound, Written

logger = logging.getLogger(__name__)

_FAILED_REASONS = {
    FinishOutcome.FAILED: DeletionReason.OUTCOME_FAILED,
    FinishOutcome.CANCELLED: DeletionReason.OUTCOME_CANCELLED,
}


class _Handled(StrEnum):
    NOTHING_WRITTEN = "nothing_written"  # 再送、遅れた通知、未知の crawl_id
    FAILED_RECORDED = "failed_recorded"  # `failed`・`cancelled` を `failed` として記録した
    QUEUED_FOR_DELETION = "queued_for_deletion"  # `enumeration_completed` を受理した


class FinishReceiver:
    def __init__(
        self,
        *,
        config: LifecycleConfig,
        results: DeletionResults,
        source_locks: SourceLocks,
        clock: Clock,
        wake: Callable[[], None],
    ) -> None:
        """`wake` は、`enumeration_completed` を受理して永続化したあとに呼ぶ(削除ワーカーを起こす)。

        例外を送出しないこと(受理は永続化済みで、応答は 202 のまま)。
        """
        self._config = config
        self._results = results
        self._source_locks = source_locks
        self._clock = clock
        self._wake = wake

    def accept(self, notification: FinishNotification) -> None:
        """終了通知を受理する(正常終了が 202)。拒否は `NotificationRejectedError`(状態は変えない)。

        書き込みが 409 で `write_conflict_max_rereads` を超えたら、何も書かずに `UnavailableError`。
        """
        with self._source_locks.hold(notification.source_id):
            handled = retry_after_conflict(
                lambda: self._try_accept(notification),
                max_rereads=self._config.write_conflict_max_rereads,
            )
        if handled is _Handled.QUEUED_FOR_DELETION:
            self._wake()

    def _try_accept(self, notification: FinishNotification) -> _Handled | Conflict:
        current = self._results.fetch_result(notification.crawl_id)
        if current is None:
            # 開始通知を受けていない `crawl_id`(K7)。結果は作らず、ID だけをログに残す(案。P16)。
            logger.info(
                "finish notification for an unknown crawl was discarded: crawl_id=%r",
                notification.crawl_id,
            )
            return _Handled.NOTHING_WRITTEN
        record = current.record
        if record.source_id != notification.source_id:
            raise FinishSourceMismatchError
        if record.finish_request_digest is not None:
            return _judge_resend(record, notification)
        if record.status.is_terminal:
            # 遅れた通知(分岐 1)。`superseded` などの旧世代で、状態を変えず削除しない。
            return _Handled.NOTHING_WRITTEN
        if notification.outcome is FinishOutcome.ENUMERATION_COMPLETED:
            return self._queue_for_deletion(current, notification)
        return self._record_failed(current, notification)

    def _queue_for_deletion(
        self, current: StoredResult, notification: FinishNotification
    ) -> _Handled | Conflict:
        outcome = self._results.replace_result(
            current, self._received(current.record, notification)
        )
        return _handled_or_conflict(outcome, _Handled.QUEUED_FOR_DELETION)

    def _record_failed(
        self, current: StoredResult, notification: FinishNotification
    ) -> _Handled | Conflict:
        """`failed`・`cancelled` は、待たずに `failed` にする(待ち行列に入れない)。

        `finish_received_at` と ID 一覧は記録せず、ダイジェストだけを同じ書き込みで保存する(K36)。
        """
        progress = replace(
            current.record,
            outcome=notification.outcome,
            finish_request_digest=notification.digest(),
        )
        outcome = self._results.transition_to_terminal(
            current,
            DeletionStatus.FAILED,
            reason=_FAILED_REASONS[notification.outcome],
            progress=progress,
        )
        return _handled_or_conflict(outcome, _Handled.FAILED_RECORDED)

    def _received(
        self, record: DeletionResultRecord, notification: FinishNotification
    ) -> DeletionResultRecord:
        """受理を記録した結果。ダイジェスト・`finish_received_at`・ID 一覧は同じ書き込みで保存する。

        両 ID 一覧の合算件数が上限を超えるときは、一覧を保存せず、件数と超過フラグだけを残す(K34)。
        """
        skipped = notification.normalized_skipped_ids() or ()
        oversize = notification.normalized_oversize_ids() or ()
        id_count = len(skipped) + len(oversize)
        limit_exceeded = id_count > self._config.skip_oversize_id_limit
        return replace(
            record,
            outcome=notification.outcome,
            enumerated_count=notification.enumerated_count,
            finish_received_at=self._clock.now(),
            finish_request_digest=notification.digest(),
            skipped_document_ids=None if limit_exceeded else skipped,
            oversize_document_ids=None if limit_exceeded else oversize,
            skip_and_oversize_id_count=id_count,
            skip_and_oversize_id_limit_exceeded=limit_exceeded,
        )


def _judge_resend(record: DeletionResultRecord, notification: FinishNotification) -> _Handled:
    """最初の通知を受理済み(ダイジェストが記録済み)の再送。世代も状態も見ずに内容だけを比べる。"""
    if record.finish_request_digest != notification.digest():
        raise FinishContentMismatchError
    return _Handled.NOTHING_WRITTEN


def _handled_or_conflict(
    outcome: Written | Conflict | NotFound, handled: _Handled
) -> _Handled | Conflict:
    # 文書なし(読んだ後に結果が消えた)も読み直す。次の判定で未知の `crawl_id` になる。
    return handled if isinstance(outcome, Written) else Conflict()
