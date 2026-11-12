"""削除ワーカー(走査型+起床通知。案 2、arch 9.9)。全ソース直列で、並行度は 1。

待ち行列は `loreley-deletions` の状態から導く(終了通知を受理済みで終端状態でない結果。
`finish_received_at` と `crawl_id` の順)。ワーカーは先頭の 1 件を `DeletionProcessor` に処理させる。
起床通知(`wake()`。終了通知の受理で呼ばれる)がなくても、`poll_interval_seconds` ごとに走査する。

処理(走査・判定・実行)が例外で失敗すると、結果は変えずに次の走査でやり直す(9.9。連続失敗で
`failed` にしたり、先頭を飛ばして次のソースへ進んだりしない。直列の意味を変えないため)。
そのため、連続して失敗している間は走査の間隔を倍々に延ばし(上限 `poll_backoff_max_seconds`)、
OpenSearch の障害中に重い判定(件数の取得・ID の取り込み)を短い間隔で繰り返さないようにする。
起床通知では、間隔の途中でも再試行する(連続失敗の回数は保つ)。成功で元の間隔に戻る。

`run_once()` は 1 ステップで、スレッドを使わずに直接呼べる(テストをスリープ・実スレッドに頼らず
決定的にするため)。スレッドは `run_once()` を繰り返すだけ。

`start()` は、起動時の整理(`CrawlRuns.fail_unfinished_crawls_after_restart()`)の後に呼ぶこと。
先に始めると、再起動前に受理した削除を再開してしまう(再開しない方針。9.8)。
"""

import logging
import threading
from collections.abc import Callable

from loreley_indexer.crawl_runs.deletion.outcome import DeletionOutcome
from loreley_indexer.crawl_runs.deletion.processor import DeletionProcessor
from loreley_indexer.crawl_runs.lifecycle import DeletionResults

logger = logging.getLogger(__name__)

STOP_JOIN_TIMEOUT_SECONDS = 10.0

# この結末のときは、すぐに次の走査へ進む(待ち行列に残りがありうる)。
_PROGRESSED = {DeletionOutcome.FINISHED, DeletionOutcome.CLOSED}


# 起床通知を最大 `seconds` 待つ。通知で戻ったら True、時間切れなら False。
WaitForWake = Callable[[float], bool]


class DeletionWorker:
    def __init__(
        self,
        *,
        poll_interval_seconds: float,
        poll_backoff_max_seconds: float,
        results: DeletionResults,
        processor: DeletionProcessor,
        wake_event: threading.Event,
        stop_event: threading.Event,
        wait: WaitForWake | None = None,
    ) -> None:
        """`wait` を省略すると `wake_event` を待つ(本番)。テストは、待たずに記録する関数を渡す。"""
        self._poll_interval_seconds = poll_interval_seconds
        self._poll_backoff_max_seconds = poll_backoff_max_seconds
        self._results = results
        self._processor = processor
        self._wake_event = wake_event
        self._stop_event = stop_event
        self._wait = wait if wait is not None else wake_event.wait
        self._consecutive_failures = 0
        self._thread: threading.Thread | None = None

    def wake(self) -> None:
        self._wake_event.set()

    def run_once(self) -> bool:
        """待ち行列の先頭を 1 件処理したら True(続けて走査する)。空・待機・失敗なら False。

        処理中の例外でスレッドを落とさない。ID と例外クラス名だけをログに出す(R9)。
        結果は変えないので、次の走査で処理し直す。
        """
        crawl_id: str | None = None
        try:
            queue = self._results.list_unfinished_received()
            progressed = False
            if queue:
                crawl_id = queue[0].crawl_id
                progressed = self._processor.process(crawl_id) in _PROGRESSED
        except Exception as error:
            self._consecutive_failures += 1
            self._log_failure(error, crawl_id)
            return False
        self._log_recovery()
        self._consecutive_failures = 0
        return progressed

    def next_wait_seconds(self) -> float:
        """次の走査までの間隔。連続して失敗しているほど長い(上限 `poll_backoff_max_seconds`)。"""
        delay = self._poll_interval_seconds
        for _ in range(self._consecutive_failures):
            delay *= 2
            if delay >= self._poll_backoff_max_seconds:
                return self._poll_backoff_max_seconds
        return delay

    def start(self) -> None:
        """スレッドを起動する。呼べるのは 1 回だけで、`stop()` のあとは再起動できない。"""
        if self._thread is not None:
            raise RuntimeError("the deletion worker is already started")
        self._thread = threading.Thread(
            target=self._run_until_stopped, name="deletion-worker", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """停止を要請し、実行中のバッチを終えてからスレッドを止める。

        再試行の待ちは中断する。処理の途中だった結果は `running` のまま残り、次の起動時の
        整理で `failed`(`indexer_restart`)になる。
        """
        self._stop_event.set()
        self._wake_event.set()
        if self._thread is not None:
            self._thread.join(STOP_JOIN_TIMEOUT_SECONDS)

    def _run_until_stopped(self) -> None:
        while not self._stop_event.is_set():
            if self.run_once():
                continue
            # 待つ前に走査した後で通知が来ても、イベントは立ったままなので取りこぼさない。
            # 通知を消すのは、待ちから戻った直後(次の走査より前)だけ。
            if self._wait(self.next_wait_seconds()):
                self._wake_event.clear()

    def _log_recovery(self) -> None:
        if self._consecutive_failures > 0:
            logger.info(
                "deletion worker recovered after %d consecutive failures",
                self._consecutive_failures,
            )

    def _log_failure(self, error: Exception, crawl_id: str | None) -> None:
        """ログ洪水を避けるため、連続失敗の 1・2・4・8… 回目だけ warning にする(ほかは debug)。"""
        is_power_of_two = self._consecutive_failures & (self._consecutive_failures - 1) == 0
        level = logging.WARNING if is_power_of_two else logging.DEBUG
        if crawl_id is None:
            logger.log(
                level,
                "deletion queue scan failed: error=%s consecutive_failures=%d",
                type(error).__name__,
                self._consecutive_failures,
            )
            return
        logger.log(
            level,
            "deletion processing failed: crawl_id=%s error=%s consecutive_failures=%d",
            crawl_id,
            type(error).__name__,
            self._consecutive_failures,
        )
