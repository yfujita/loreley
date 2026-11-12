"""要約ワーカー(有界。arch 7.2、K49)。

`run_once()` は 1 ステップ(依頼 1 件の処理、または依頼がなければ再走査の要否の確認)で、
スレッドを使わずに直接呼べる(テストをスリープ・実スレッドに頼らず決定的にするため)。
スレッドは `run_once()` を繰り返すだけ。
"""

import logging
import threading

from loreley_indexer.documents.summarization.processor import SummaryProcessor
from loreley_indexer.documents.summarization.request_queue import SummaryRequestQueue
from loreley_indexer.documents.summarization.rescanner import SummaryRescanner
from loreley_indexer.documents.summarization.status import SummaryOutcome

logger = logging.getLogger(__name__)

IDLE_WAIT_SECONDS = 1.0
STOP_JOIN_TIMEOUT_SECONDS = 10.0


class SummaryWorkerPool:
    def __init__(
        self,
        *,
        concurrency: int,
        requests: SummaryRequestQueue,
        processor: SummaryProcessor,
        rescanner: SummaryRescanner,
        stop_event: threading.Event,
    ) -> None:
        self._concurrency = concurrency
        self._requests = requests
        self._processor = processor
        self._rescanner = rescanner
        self._stop_event = stop_event
        self._threads: list[threading.Thread] = []

    def run_once(self, wait_seconds: float = 0.0) -> bool:
        """依頼を 1 件処理したら True。なければ `wait_seconds` まで待ち、それでもなければ False。

        依頼がないときは、待つ前に再走査の要否を確認する(再走査が積んだ依頼はそのまま処理する)。
        要約の失敗はここで止める。ワーカーのスレッドを落とさず、登録にも影響させない。
        """
        document_id = self._requests.take()
        if document_id is None:
            self._rescan_if_needed()
            document_id = self._requests.take(wait_seconds)
        if document_id is None:
            return False
        try:
            outcome = self._processor.process(document_id)
        except Exception as error:
            # OpenSearch の全体異常や LLM クライアントの想定外の例外。文書は `pending` のまま残る。
            logger.warning(
                "summary processing failed: document_id=%s error=%s",
                document_id,
                type(error).__name__,
            )
            self._rescanner.request()
            return True
        if outcome is SummaryOutcome.WRITTEN:
            self._rescanner.note_summary_written()
        if outcome.needs_rescan:
            self._rescanner.request()
        return True

    def start(self) -> None:
        """ワーカーのスレッドを起動する。呼べるのは 1 回だけで、`stop()` のあとは再起動できない。"""
        for number in range(self._concurrency):
            thread = threading.Thread(
                target=self._run_until_stopped, name=f"summary-worker-{number}", daemon=True
            )
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        """実行中の処理を終えてからスレッドを止める。再 `start()` はできない。"""
        self._stop_event.set()
        self._requests.close()
        for thread in self._threads:
            thread.join(STOP_JOIN_TIMEOUT_SECONDS)
        self._threads.clear()

    def _run_until_stopped(self) -> None:
        while not self._stop_event.is_set():
            self.run_once(wait_seconds=IDLE_WAIT_SECONDS)

    def _rescan_if_needed(self) -> None:
        if self._requests.take_overflow_flag():
            self._rescanner.request()
        try:
            self._rescanner.run_if_due()
        except Exception as error:
            logger.warning("summary rescan failed: error=%s", type(error).__name__)
