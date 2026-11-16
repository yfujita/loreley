"""Scheduler: 定期クロールの起動時刻を判定し、`jobs` の受付を呼ぶ(module 4.2・5.8。arch 4.3)。

一定の周期(tick)で起き、`schedule_cron` が設定された `active` のソースごとに、起動してよいかを
判定する。

- メモリ上に「前回の判定時刻」(`last_checked`)だけを持つ。プロセスの起動時(`start` の時点。
  組み立て・起動時の回復が終わった後)の時刻で初期化する。各 tick で、`last_checked` より後で
  最初に cron 式に合う時刻(`LORELEY_CRAWLER_TIMEZONE` の暦で解釈。全ソース共通)が現在以前なら、
  `jobs` の定期の受付(`accept_scheduled_crawl`)を呼ぶ。tick の間に複数の時刻が過ぎても、起動は
  1 回。判定のあとで `last_checked` を現在に進める。
- Crawler が動いていない間(停止・再起動・回復中)に過ぎた時刻は起動しない(`last_checked` が
  起動時刻から始まるため)。ジョブ記録の `queued_at` や設定の登録・更新時刻は基準にしない
  (手動クロールの直後でも、cron の時刻には起動する)。
- 受付の拒否(ロック保持中・メンテナンス・削除中・設定なし)は、その時刻は何もせず見送る。待ち行列を
  作らず、見送った時刻は取り返さない(`last_checked` が進むため)。
- 時計が戻った(現在 < `last_checked`)tick は、`last_checked` を現在にそろえるだけで起動しない
  (安全側。戻った tick では起動しない。戻った区間を時計が再び通過したときは、すでに起動した時刻を
  再度起動しうる=既知の制約。運用では時計を戻さない前提)。
- ソース一覧の読み取りに失敗した tick は、`last_checked` を進めない(判定していない時刻を、次の
  tick が判定する。Crawler は動いていたので、取りこぼさない)。
- Store 層の異常・想定外の例外では落ちない。ログ(固定の語彙。例外の種類だけ)を出して、そのソース
  (一覧の失敗なら全体)を見送り、次の周期を待つ。ログに設定の値・Connector の設定は出さない(R11)。

スレッドは 1 つ(daemon)。`run_once`(1 周)をスレッドなしで呼べるので、判定は決定的に確かめられる。
Scheduler は受付の判断・ジョブ記録の書き込み・ジョブの実行をしない(R4)。
"""

import logging
import threading
from datetime import datetime

from loreley_crawler.common.clock import Clock
from loreley_crawler.common.errors import (
    StoreUnavailableError,
    StoreUnexpectedResponseError,
    is_store_unavailable,
)
from loreley_crawler.common.retry import Retrier
from loreley_crawler.jobs import (
    Accepted,
    AdmissionResult,
    EventTickWaiter,
    JobAdmission,
    LockAlreadyHeld,
    MaintenanceEnabled,
    SourceConfigNotFound,
    SourceDeleting,
    TickWaiter,
    loggable_id,
)
from loreley_crawler.scheduler.settings import SchedulerSettings
from loreley_crawler.sources import (
    InvalidScheduleCron,
    SourceReader,
    SourceRecord,
    StoredSource,
    next_fire_time,
)

logger = logging.getLogger(__name__)

# 受付の拒否の種類 → ログの固定の語彙。
_REJECTION_NAMES: dict[type, str] = {
    SourceConfigNotFound: "source_config_not_found",
    SourceDeleting: "source_deleting",
    MaintenanceEnabled: "maintenance_enabled",
    LockAlreadyHeld: "lock_held",
}


_ROUTINE_REJECTIONS = (LockAlreadyHeld, MaintenanceEnabled, SourceDeleting)


def _describe(error: Exception) -> str:
    """ログ用の種別名。例外のクラス名と、固定の理由名・種別名だけ(値・メッセージは出さない。R11)。"""
    if isinstance(error, StoreUnexpectedResponseError):
        return f"{type(error).__name__}({error.error_type})"
    if isinstance(error, StoreUnavailableError):
        return f"{type(error).__name__}({error.reason})"
    return type(error).__name__


class Scheduler:
    def __init__(
        self,
        *,
        settings: SchedulerSettings,
        source_reader: SourceReader,
        admission: JobAdmission,
        clock: Clock,
        retrier: Retrier,
        waiter: TickWaiter | None = None,
    ) -> None:
        self._settings = settings
        self._source_reader = source_reader
        self._admission = admission
        self._clock = clock
        self._retrier = retrier
        # `start` でも設定し直す。ここは、`start` を経ずに `run_once` を呼ぶ使い方のための初期値。
        self._last_checked = clock.now()
        self._waiter = waiter or EventTickWaiter()
        self._stop_requested = threading.Event()
        self._thread: threading.Thread | None = None

    # --- スレッドの開始・停止 ---

    def start(self) -> None:
        """専用のスレッド(daemon)で `run_until_stopped` を始める。"""
        if self._thread is not None:
            raise RuntimeError("the scheduler is already started")
        # 組み立てから `start` までの間(起動時の回復など)に過ぎた時刻は起動しない。
        self._last_checked = self._clock.now()
        self._thread = threading.Thread(
            target=self.run_until_stopped, name="scheduler", daemon=True
        )
        self._thread.start()

    def request_stop(self) -> None:
        """停止を要求する。待ちの途中でも、すぐに戻る(1 周の途中なら、次のソースの前に止まる)。"""
        self._stop_requested.set()
        self._waiter.stop()

    def join(self, timeout_seconds: float) -> bool:
        """スレッドの終了を `timeout_seconds` まで待つ。終わっていれば True。"""
        if self._thread is None:
            return True
        self._thread.join(timeout=timeout_seconds)
        return not self._thread.is_alive()

    def run_until_stopped(self) -> None:
        while not self._stop_requested.is_set():
            self.run_once()
            if self._waiter.wait(self._settings.check_interval_seconds):
                return

    # --- 1 周 ---

    def run_once(self) -> None:
        """対象のソースを 1 周する。例外は外に出さない(次の周期で、判定し直す)。"""
        now = self._clock.now()
        if now < self._last_checked:
            self._last_checked = now
            return
        try:
            sources = self._retrier.run(
                self._source_reader.list_scheduled_active_sources,
                is_retryable_error=is_store_unavailable,
            )
        except Exception as error:
            logger.warning("scheduler could not list the sources: error=%s", _describe(error))
            return
        for source in sources:
            if self._stop_requested.is_set():
                return
            try:
                self._schedule(source, checked_after=self._last_checked, now=now)
            except Exception as error:
                # 他のソースの判定を止めない。例外の種類だけを出す。
                logger.warning(
                    "scheduler skipped a source because of an error: source_id=%s error=%s",
                    loggable_id(source.source_id),
                    _describe(error),
                )
        self._last_checked = now

    def _schedule(self, source: StoredSource, *, checked_after: datetime, now: datetime) -> None:
        if not isinstance(source, SourceRecord):
            # 周期が読めない。管理者が設定を直すまで起動しない(項目名だけを出す)。
            logger.warning(
                "scheduler skipped a malformed source config: source_id=%s invalid_fields=%s",
                loggable_id(source.source_id),
                ",".join(source.invalid_fields),
            )
            return
        cron = source.schedule_cron
        if cron is None:
            return
        try:
            first_fire_time = next_fire_time(
                cron, after=checked_after, zone=self._settings.timezone
            )
        except InvalidScheduleCron:
            # 保存時に検証済みなので通常は起きない(合う時刻が探索の範囲にないときなど)。
            logger.warning(
                "scheduler skipped a source with no next fire time: source_id=%s",
                loggable_id(source.source_id),
            )
            return
        # どちらも aware な時刻なので、タイムゾーンによらず瞬間として比べられる。
        if first_fire_time > now:
            return
        self._log_result(source.source_id, self._admission.accept_scheduled_crawl(source.source_id))

    @staticmethod
    def _log_result(source_id: str, result: AdmissionResult) -> None:
        if isinstance(result, Accepted):
            logger.info(
                "scheduled crawl accepted: source_id=%s job_id=%s",
                loggable_id(source_id),
                loggable_id(result.job.job_id),
            )
            return
        rejection = _REJECTION_NAMES.get(type(result), "unknown")
        # 状態が続く間は cron の時刻のたびに出るので、見送り(ロック・メンテナンス・削除中)は
        # DEBUG にする(受付の判断の結果で、運用者が気づく異常ではない)。
        level = logging.DEBUG if isinstance(result, _ROUTINE_REJECTIONS) else logging.INFO
        logger.log(
            level,
            "scheduled crawl skipped: source_id=%s reason=%s",
            loggable_id(source_id),
            rejection,
        )
