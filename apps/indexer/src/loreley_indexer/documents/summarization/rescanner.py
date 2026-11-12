"""`pending` の文書の再走査(arch 7.4、P15)。

Indexer の再起動後、生成・書き戻しが `pending` のまま終わったとき、
キューが満杯で依頼を断ったときに、`summary_status=pending` の文書を ID だけ列挙して再び依頼する。
`disabled`(要約が無効、`extract_failed`)と `failed` は対象にしない。
走査どうしの間隔には下限を置く(失敗し続ける LLM を叩き続けないため)。
書き戻しに成功しない走査が続くと、間隔を 2 倍ずつ上限まで伸ばす(LLM の設定の食い違いや
メンテナンスの長期化で、全 `pending` の再生成を一定間隔で繰り返し続けないため)。
書き戻しに 1 件でも成功すれば、間隔は下限に戻る。最初の走査(起動時の要請)はいつでも即時に行う。
"""

import logging
import threading
from datetime import datetime

from loreley_indexer.common.clock import Clock
from loreley_indexer.documents.summarization.config import SummarizationConfig
from loreley_indexer.documents.summarization.request_queue import (
    SubmitResult,
    SummaryRequestQueue,
)
from loreley_indexer.documents.summarization.status import SummaryStatus
from loreley_indexer.infrastructure.opensearch import DocumentFilter, SearchIndexRepository

logger = logging.getLogger(__name__)


class SummaryRescanner:
    def __init__(
        self,
        *,
        config: SummarizationConfig,
        search_index: SearchIndexRepository,
        requests: SummaryRequestQueue,
        clock: Clock,
    ) -> None:
        self._config = config
        self._search_index = search_index
        self._requests = requests
        self._clock = clock
        self._lock = threading.Lock()
        self._requested = False
        self._last_run_at: datetime | None = None
        self._written_since_last_scan = False
        self._scans_without_progress = 0

    def request(self) -> None:
        """次に間隔の下限を満たしたときに走査する。起動時と、`pending` が残ったときに呼ぶ。"""
        with self._lock:
            self._requested = True

    def note_summary_written(self) -> None:
        """要約の書き戻しに成功したことを知らせる。再走査の間隔を下限に戻す。"""
        with self._lock:
            self._written_since_last_scan = True
            self._scans_without_progress = 0

    def run_if_due(self) -> int:
        """要請があり、前回の走査から必要な間隔が過ぎていれば走査する。依頼した件数を返す。

        必要な間隔は、下限から始まり、成果のない走査が続くたびに 2 倍になる(上限あり)。
        """
        with self._lock:
            if not self._requested:
                return 0
            now = self._clock.now()
            if self._last_run_at is not None:
                elapsed_seconds = (now - self._last_run_at).total_seconds()
                if elapsed_seconds < self._required_interval_seconds():
                    return 0
                if not self._written_since_last_scan:
                    self._scans_without_progress += 1
            self._requested = False
            self._last_run_at = now
            self._written_since_last_scan = False
        try:
            return self._scan()
        except Exception:
            self.request()  # 失敗した走査は、次の機会にやり直す。
            raise

    def _required_interval_seconds(self) -> float:
        # 指数が大きくなっても上限で止まる。巨大な冪を作らないよう、先に上限で打ち切る。
        interval = self._config.rescan_min_interval_seconds
        for _ in range(self._scans_without_progress):
            interval *= 2
            if interval >= self._config.rescan_max_interval_seconds:
                break
        return min(interval, self._config.rescan_max_interval_seconds)

    def _scan(self) -> int:
        document_filter = DocumentFilter(summary_status=SummaryStatus.PENDING)
        accepted = 0
        after: str | None = None
        while True:
            page = self._search_index.search_document_ids(
                document_filter, page_size=self._config.rescan_page_size, after=after
            )
            for document_id in page:
                result = self._requests.submit(document_id)
                if result is SubmitResult.FULL:
                    # 残りは、キューが空いたあとの次の走査に委ねる。
                    self.request()
                    logger.info("summary rescan stopped: queue is full (accepted=%d)", accepted)
                    return accepted
                if result is SubmitResult.ACCEPTED:
                    accepted += 1
            if len(page) < self._config.rescan_page_size:
                return accepted
            after = page[-1]
