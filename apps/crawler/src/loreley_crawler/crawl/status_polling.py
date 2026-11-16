"""削除結果のポーリングと、確認結果の区分(architecture 7.6。CA-K-3・CA-K-4・CA-P-30・CA-P-32)。

終了通知(`enumeration_completed`)の 202 を確認した後、Status API の `status` が終端状態
(`running` 以外)になるまで、一定の間隔でポーリングする(待機中の `waiting_for` ありも `running`)。
- 待ちは `JobContext.wait`(既定の確認点は所有・取り消し。ハートビートは別スレッドで続く)
- ポーリングの失敗(タイムアウト・接続エラー・5xx・404 など)は、成功の応答が入るたびに
  連続を数え直す。連続が `polling_max_consecutive_failures` に達する、または全体の上限時間を
  超えたら、確認を打ち切る
- **打ち切っても、ジョブの status は変えず、再確認しない**(確定。CA-K-4)。区分と警告だけ残す

区分:
- `confirmed`: 削除結果が終端状態になったことを確認できた
- `unknown`: 404 だけが、連続回数に達するまで続いた(消えた・記録を失った。区別できない)
- `unconfirmed`: 上限時間を超えた。または連続した失敗に 404 以外が 1 つでも含まれて連続回数に達した

**202 は受理の確認ではない**: 最初の成功の応答で、受理の根拠(`finish_received_at` があること、
または `status=failed` かつ `reason` が `outcome_failed`・`outcome_cancelled`)を確かめる。
根拠がなければ警告(`finish_not_acknowledged`)を残す。ポーリングは続ける(終端状態なら `confirmed`)。
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from loreley_crawler.common.clock import Clock
from loreley_crawler.common.display_text import format_display_text
from loreley_crawler.common.timestamps import format_instant
from loreley_crawler.crawl.indexer_calls import IndexerCaller
from loreley_crawler.crawl.settings import CrawlSettings
from loreley_crawler.crawl.warning_log import FINISH_NOT_ACKNOWLEDGED, POLLING_ABORTED, WarningLog
from loreley_crawler.infrastructure.indexer_client import (
    CrawlStatus,
    IndexerRejected,
    IndexerUnavailable,
)
from loreley_crawler.jobs import Check, JobContext

RUNNING = "running"
_ACKNOWLEDGING_FAILURE_REASONS = frozenset({"outcome_failed", "outcome_cancelled"})
# Indexer が返す文字列は、記録の前に表示用に整形する(R11。長さの上限)。
_SUMMARY_TEXT_MAX_CHARS = 64


class DeletionConfirmation(StrEnum):
    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PollingResult:
    """確認結果の区分と、最後に読めた Status(一度も読めなければ None)。

    `observed_at` は、最後に読めた日時(ジョブ記録の `deletion_summary` に、打ち切ったときだけ写す)。
    """

    confirmation: DeletionConfirmation
    last_status: CrawlStatus | None
    observed_at: str | None


class StatusPoller:
    def __init__(
        self,
        *,
        context: JobContext,
        indexer: IndexerCaller,
        settings: CrawlSettings,
        clock: Clock,
        warnings: WarningLog,
    ) -> None:
        self._context = context
        self._indexer = indexer
        self._settings = settings
        self._clock = clock
        self._warnings = warnings
        self.is_started = False
        self._last_status: CrawlStatus | None = None
        self._observed_at: str | None = None

    def poll(self) -> PollingResult:
        """終端状態を確認するか、確認を打ち切るまでポーリングする。

        取り消し・所有権の喪失は、待ちの確認点が例外で知らせる(呼び出し側が扱う)。
        """
        self.is_started = True
        # 2 回目以降の確認は待ちが行う。最初の要請の前にも、所有と取り消しを確認する。
        self._context.check(Check.OWNERSHIP | Check.CANCELLATION)
        started_at = self._clock.now()
        failures = _FailureStreak(self._settings.polling_max_consecutive_failures)
        is_first_success = True
        while True:
            reply = self._indexer.get_status()
            if isinstance(reply, CrawlStatus):
                failures.record_success()
                self._last_status = reply
                self._observed_at = format_instant(self._clock.now())
                if is_first_success:
                    is_first_success = False
                    self._check_acknowledged(reply)
                if reply.status != RUNNING:
                    return self._result(DeletionConfirmation.CONFIRMED)
            elif failures.record_failure(reply):
                return self._abort(failures.confirmation)
            elapsed_seconds = (self._clock.now() - started_at).total_seconds()
            if elapsed_seconds >= self._settings.polling_timeout_seconds:
                return self._abort(DeletionConfirmation.UNCONFIRMED)
            self._context.wait(self._settings.polling_interval_seconds)

    def abort_on_cancel(self) -> PollingResult | None:
        """ポーリング中に取り消されたとき、確認を打ち切る(`unconfirmed`。警告を残す)。

        ポーリングに入っていなければ None。
        """
        if not self.is_started:
            return None
        self._warnings.add(POLLING_ABORTED, confirmation=DeletionConfirmation.UNCONFIRMED.value)
        return self._result(DeletionConfirmation.UNCONFIRMED)

    def _check_acknowledged(self, status: CrawlStatus) -> None:
        """終了通知の受理の根拠を確かめる。根拠がなければ警告を残す(ポーリングは続ける)。"""
        has_receipt = status.finish_received_at is not None
        acknowledged_as_failed = (
            status.status == "failed" and status.reason in _ACKNOWLEDGING_FAILURE_REASONS
        )
        if not (has_receipt or acknowledged_as_failed):
            self._warnings.add(FINISH_NOT_ACKNOWLEDGED)

    def _abort(self, confirmation: DeletionConfirmation) -> PollingResult:
        self._warnings.add(POLLING_ABORTED, confirmation=confirmation.value)
        return self._result(confirmation)

    def _result(self, confirmation: DeletionConfirmation) -> PollingResult:
        return PollingResult(confirmation, self._last_status, self._observed_at)


class _FailureStreak:
    """成功の応答が入るたびに数え直す、ポーリングの失敗の連続(architecture 7.6)。"""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._count = 0
        self._has_non_404_failure = False

    def record_success(self) -> None:
        self._count = 0
        self._has_non_404_failure = False

    def record_failure(self, reply: IndexerUnavailable | IndexerRejected) -> bool:
        """失敗を数え、連続が規定の回数に達したら True を返す。"""
        self._count += 1
        is_404 = isinstance(reply, IndexerRejected) and reply.status_code == 404
        self._has_non_404_failure = self._has_non_404_failure or not is_404
        return self._count >= self._limit

    @property
    def confirmation(self) -> DeletionConfirmation:
        """404 だけが続いたなら `unknown`、そうでなければ `unconfirmed`。"""
        if self._has_non_404_failure:
            return DeletionConfirmation.UNCONFIRMED
        return DeletionConfirmation.UNKNOWN


def deletion_summary_record(result: PollingResult) -> dict[str, Any] | None:
    """ジョブ記録の `deletion_summary`(architecture 7.6。JSON の型)。

    最後に読めた応答の項目を写す(値のない項目は省く)。打ち切ったときは、読めた日時も添える。
    一度も読めていなければ None。
    """
    status = result.last_status
    if status is None:
        return None
    candidates = {
        "status": status.status,
        "reason": status.reason,
        "forced": status.forced,
        "target_count": status.target_count,
        "denominator": status.denominator,
        "deleted_count": status.deleted_count,
        "enumerated_count": status.enumerated_count,
        "n_seen": status.n_seen,
        "e_missing": status.e_missing,
        "finish_received_at": status.finish_received_at,
        "deletion_started_at": status.deletion_started_at,
        "finished_at": status.finished_at,
    }
    summary = {name: _displayable(value) for name, value in candidates.items() if value is not None}
    if result.confirmation is not DeletionConfirmation.CONFIRMED and result.observed_at:
        summary["observed_at"] = result.observed_at
    return summary


def _displayable(value: object) -> object:
    if isinstance(value, str):
        return format_display_text(value, max_chars=_SUMMARY_TEXT_MAX_CHARS)
    return value
