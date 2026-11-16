"""`JobContext`: 実行対象(`crawl`・`source_delete`)に渡す、ジョブ単位の部品(module 4.4。CM-P-16)。

Job Runner のスレッドだけが使う(スレッドをまたいで共有しない)。提供するもの:
- 版条件つきのジョブ記録の更新。条件が外れたら読み直し、状態が `failed`(`lock_released`)などに
  変わっていれば、所有権の喪失(`OwnershipLost`)として知らせる(architecture 5.3 の書き手の表)
- 確認点(`check`): 所有の確認(I/O なし)・取り消し要求の確認・メンテナンスフラグの確認。
  どの呼び出しの前でどれを確認するかは、実行対象が決める(`Check`)。それぞれ例外で知らせる
- 確認点を通しながら中断できる待ち(`wait`)と、確認点つきのリトライ(`retrier`)
- `queued` -> `running`(`start_running`)、`settings_snapshot`・`settings_source_updated_at` の追記、
  最終状態の記録(`finish`)

`connector_config` は持たない(中身を知らない。保持先は `crawl` の実行状態。CM-P-22)。ジョブ記録に
書く項目にも含められない。ロックの解放は Job Runner が行う(実行対象は最終状態の記録まで)。
"""

import dataclasses
from collections.abc import Callable, Mapping
from datetime import datetime
from enum import Flag
from typing import Any

from loreley_crawler.common.clock import Clock
from loreley_crawler.common.display_text import format_display_text
from loreley_crawler.common.errors import is_store_unavailable
from loreley_crawler.common.retry import Retrier, wait_with_checkpoint
from loreley_crawler.common.timestamps import format_instant
from loreley_crawler.jobs.cancel_requests import CancelRequestRegistry
from loreley_crawler.jobs.interruptions import (
    CancellationRequested,
    JobNotStartable,
    MaintenanceDetected,
    OwnershipLost,
)
from loreley_crawler.jobs.job_updates import Applied, NotApplicable, apply_job_update
from loreley_crawler.jobs.locks import Heartbeat
from loreley_crawler.jobs.records import FailureReason, JobRecord, JobRecordStore, JobStatus

# 喪失の理由(`Heartbeat` の理由に加える。固定の名前)。
LOSS_LOCK_NOT_OWNED = "lock_not_owned"
LOSS_JOB_RECORD_SUPERSEDED = "job_record_superseded"

# CA-K-5 で確定した設定スナップショットの 6 項目。丸ごと Indexer に送るので、7 番目を入れない。
SETTINGS_SNAPSHOT_KEYS = frozenset(
    {
        "crawl_started_at",
        "ttl",
        "ratio_threshold",
        "min_delete_count",
        "force_delete",
        "rewrite_mode",
    }
)

# `failure_detail` 全体の長さの上限(architecture 11章の仮値)。
FAILURE_DETAIL_MAX_CHARS = 512

# `update` で書けない項目: 状態は `start_running`・`finish` で、`connector_config` は書かない。
_PROTECTED_FIELDS = frozenset({"status", "connector_config"})

_RUNNING_PHASE = (JobStatus.RUNNING,)
# 最終状態は、`queued` からも書ける。Job Runner が、実行を始められなかったジョブ(実行対象が
# `running` にする前に例外を送出した場合)を最後の手段で `failed` にするため。
_BEFORE_OR_DURING_RUN = (JobStatus.QUEUED, JobStatus.RUNNING)


class Check(Flag):
    """確認点で確認するもの。呼び出しごとに、実行対象が選ぶ。"""

    OWNERSHIP = 1
    CANCELLATION = 2
    MAINTENANCE = 4

    ALL = 7


class JobContext:
    def __init__(
        self,
        *,
        record: JobRecord,
        job_store: JobRecordStore,
        heartbeat: Heartbeat,
        cancel_requests: CancelRequestRegistry,
        read_maintenance_flag: Callable[[], bool],
        clock: Clock,
        retrier: Retrier,
    ) -> None:
        self._record = record
        self._job_store = job_store
        self._heartbeat = heartbeat
        self._cancel_requests = cancel_requests
        self._read_maintenance_flag = read_maintenance_flag
        self._clock = clock
        # 確認点のないリトライ。ジョブ記録・メンテナンスフラグの読み書きの、Store 層の異常に使う
        # (最終状態の記録は、取り消しや所有権の喪失の後にも行うので、確認点を通さない)。
        self._base_retrier = retrier
        self._store_retrier = dataclasses.replace(retrier, checkpoint=_no_checkpoint)
        self._is_terminal = False

    @property
    def record(self) -> JobRecord:
        """最後に書いた(または読んだ)ジョブ記録。"""
        return self._record

    @property
    def job_id(self) -> str:
        return self._record.job_id

    @property
    def is_terminal(self) -> bool:
        """ジョブが終端状態になったと分かっている(最終状態を記録した、または他者が終端にした)。"""
        return self._is_terminal

    # --- 確認点・待ち・リトライ ---

    def check(self, checks: Check = Check.ALL) -> None:
        """確認点。所有・取り消し・メンテナンスの順に確認し、最初に当たったものを例外で知らせる。"""
        if Check.OWNERSHIP in checks and not self._heartbeat.is_owned():
            # 喪失の記録がなければ、最後に成功したリース期限を過ぎている(ハートビートが止まった)。
            raise OwnershipLost(self._heartbeat.lost_reason or "lease_expired")
        if Check.CANCELLATION in checks and self._cancel_requests.is_requested(self.job_id):
            raise CancellationRequested
        if Check.MAINTENANCE in checks and self._is_maintenance_enabled():
            raise MaintenanceDetected

    def retrier(self, checks: Check = Check.ALL) -> Retrier:
        """各試行の前と待ちの途中で、`checks` の確認点を通す `Retrier`(R8)。"""
        return dataclasses.replace(self._base_retrier, checkpoint=lambda: self.check(checks))

    def wait(self, seconds: float, checks: Check = Check.OWNERSHIP | Check.CANCELLATION) -> None:
        """`seconds` 待つ。待ちの途中で、一定の間隔で確認点を通し、中断があれば例外で戻る。

        ハートビートは別のスレッドで続くので、待ちの間もリースは切れない。メンテナンスフラグは
        Store 層を読むので、既定では確認しない(ポーリングの待ちなどで毎回読まないため)。
        """
        wait_with_checkpoint(
            seconds,
            checkpoint=lambda: self.check(checks),
            sleep=self._base_retrier.sleep,
            slice_seconds=self._base_retrier.wait_slice_seconds,
        )

    def record_lock_not_owned(self) -> None:
        """Indexer の `lock_not_owned` を受けたことを、所有権の喪失として記録する(5.7)。

        以後、確認点が `OwnershipLost` を送出し、Job Runner はロック文書を削除しない。
        """
        self._heartbeat.record_loss(LOSS_LOCK_NOT_OWNED)

    # --- ジョブ記録の更新 ---

    def start_running(self) -> str:
        """`queued` -> `running` にし、`started_at` を書く。`started_at` の文字列を返す。

        返す値は `crawl_started_at`(設定スナップショットと、Indexer への要請の全部で同じ文字列)
        に使う(CA-P-14)。条件付き更新に負けた(取り消された)ときは `JobNotStartable`。
        実行対象は捕捉しない。Job Runner が、ロックを解放して止める(architecture 4.5 の手順 6)。
        """
        started_at = format_instant(self._clock.now())
        outcome = self._apply(
            {"status": JobStatus.RUNNING.value, "started_at": started_at},
            applicable_statuses=(JobStatus.QUEUED,),
        )
        if isinstance(outcome, NotApplicable):
            current = outcome.current
            status = current.status if current is not None else None
            self._is_terminal = status is not None and status.is_terminal
            raise JobNotStartable(status)
        self._record = outcome.record
        return started_at

    def record_settings(
        self, settings_snapshot: Mapping[str, Any], settings_source_updated_at: datetime
    ) -> None:
        """設定スナップショット(6 項目)と、読んだ設定の `updated_at` を追記する(1 度だけ)。

        `settings_source_updated_at` は、`settings_snapshot` の外の最上位項目(診断用。CA-P-51)。
        """
        if set(settings_snapshot) != SETTINGS_SNAPSHOT_KEYS:
            raise ValueError("settings_snapshot must have exactly the six fields of CA-K-5")
        if "settings_snapshot" in self._record.fields:
            raise RuntimeError("settings_snapshot is written only once")
        self.update(
            {
                "settings_snapshot": dict(settings_snapshot),
                "settings_source_updated_at": format_instant(settings_source_updated_at),
            }
        )

    def update(self, changes: Mapping[str, Any]) -> JobRecord:
        """`running` のジョブ記録を、最後に書いた版を条件に更新する(登録結果・終了通知など)。

        条件が外れたら読み直し、`running` のままなら読み直した版でやり直す。状態が変わっていた
        (`failed`(`lock_released`)など)・記録が消えていたら、所有権の喪失として記録し
        `OwnershipLost`。Store 層の異常は、リトライを尽くして `StoreUnavailableError`。
        """
        protected = _PROTECTED_FIELDS & set(changes)
        if protected:
            raise ValueError(f"fields not writable by update: {sorted(protected)}")
        outcome = self._apply(changes, applicable_statuses=_RUNNING_PHASE)
        if isinstance(outcome, NotApplicable):
            self._record_superseded(outcome)
            raise OwnershipLost(LOSS_JOB_RECORD_SUPERSEDED)
        self._record = outcome.record
        return outcome.record

    def finish(
        self,
        status: JobStatus,
        *,
        failure_reason: FailureReason | None = None,
        failure_detail: str | None = None,
        changes: Mapping[str, Any] | None = None,
    ) -> bool:
        """最終状態(終端)を記録する。記録したら True。

        `finished_at` を書く。`failed` は `failure_reason` が必須(それ以外は付けない)。
        `failure_detail` は、保存の前に表示用の整形(切り詰め・制御文字・孤立サロゲート)を通す。
        状態がすでに他者に変えられていた(`failed`(`lock_released`)など)・記録が消えていた
        ときは、上書きせずに False(所有権の喪失として記録する)。ジョブが終端になったので、
        取り消し要求を消す。

        **最終状態は 1 度だけ**: すでに終端と分かっている(自分が記録した、または他者が終端に
        した)ときは、何も書かずに False を返す(喪失も記録しない)。最終状態を記録した後に
        実行対象が例外を送出しても、Job Runner の最後の手段が `failed` で上書きしないため。
        """
        if self._is_terminal:
            return False
        if not status.is_terminal:
            raise ValueError("status must be a terminal status")
        if (status is JobStatus.FAILED) != (failure_reason is not None):
            raise ValueError("failure_reason is required for failed, and only for failed")
        protected = _PROTECTED_FIELDS & set(changes or {})
        if protected:
            raise ValueError(f"fields not writable by finish: {sorted(protected)}")
        fields: dict[str, Any] = {
            **(changes or {}),
            "status": status.value,
            "finished_at": format_instant(self._clock.now()),
        }
        if failure_reason is not None:
            fields["failure_reason"] = failure_reason.value
        if failure_detail is not None:
            fields["failure_detail"] = format_display_text(
                failure_detail, max_chars=FAILURE_DETAIL_MAX_CHARS
            )
        outcome = self._apply(fields, applicable_statuses=_BEFORE_OR_DURING_RUN)
        if isinstance(outcome, NotApplicable):
            self._record_superseded(outcome)
            return False
        self._record = outcome.record
        self._is_terminal = True
        self._cancel_requests.clear(self.job_id)
        return True

    # --- 内部 ---

    def _apply(
        self, changes: Mapping[str, Any], *, applicable_statuses: tuple[JobStatus, ...]
    ) -> Applied | NotApplicable:
        return apply_job_update(
            self._job_store,
            self._store_retrier,
            self._record,
            changes,
            applicable_statuses=applicable_statuses,
        )

    def _record_superseded(self, outcome: NotApplicable) -> None:
        """他者がジョブ記録の状態を変えた(または消した)。所有権の喪失として記録する。"""
        current = outcome.current
        self._is_terminal = current is not None and current.status.is_terminal
        self._heartbeat.record_loss(LOSS_JOB_RECORD_SUPERSEDED)

    def _is_maintenance_enabled(self) -> bool:
        return self._store_retrier.run(
            self._read_maintenance_flag, is_retryable_error=is_store_unavailable
        )


def _no_checkpoint() -> None:
    return None
