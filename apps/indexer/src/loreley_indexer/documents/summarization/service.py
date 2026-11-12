"""要約生成の組み立てと、`documents` が公開する入口(module 4.3、M-12)。"""

import threading

from loreley_indexer.common.clock import Clock
from loreley_indexer.documents.summarization.config import SummarizationConfig
from loreley_indexer.documents.summarization.processor import SummaryProcessor
from loreley_indexer.documents.summarization.request_queue import SummaryRequestQueue
from loreley_indexer.documents.summarization.rescanner import SummaryRescanner
from loreley_indexer.documents.summarization.worker import SummaryWorkerPool
from loreley_indexer.infrastructure.llm import LlmClient
from loreley_indexer.infrastructure.opensearch import JobsReader, SearchIndexRepository


class Summarization:
    """生成依頼キュー、ワーカー、再走査をまとめる。

    登録の処理は `requests` に依頼を積む。`main.py` は `start()` で起動し、`stop()` で止める。
    `start()` は再走査を要請するので、起動時の再走査は受け付けと並行してワーカーが行う。
    `workers` と `rescanner` は、スレッドを起動せずに `run_once()` で進めるテストのために公開する。
    """

    def __init__(
        self,
        *,
        config: SummarizationConfig,
        requests: SummaryRequestQueue,
        rescanner: SummaryRescanner,
        workers: SummaryWorkerPool,
    ) -> None:
        self._config = config
        self.requests = requests
        self.rescanner = rescanner
        self.workers = workers

    def start(self) -> None:
        """要約が無効なら何もしない(LLM を呼ばず、スレッドも作らない)。

        呼べるのは 1 回だけで、`stop()` のあとの再起動はできない(停止要請のイベントを戻さないため)。
        """
        if not self._config.enabled:
            return
        self.rescanner.request()
        self.workers.start()

    def stop(self) -> None:
        self.workers.stop()


def create_summarization(
    config: SummarizationConfig,
    *,
    search_index: SearchIndexRepository,
    jobs: JobsReader,
    llm: LlmClient,
    clock: Clock,
) -> Summarization:
    stop_event = threading.Event()
    requests = SummaryRequestQueue(config.queue_size)
    rescanner = SummaryRescanner(
        config=config, search_index=search_index, requests=requests, clock=clock
    )
    processor = SummaryProcessor(
        config=config,
        search_index=search_index,
        jobs=jobs,
        llm=llm,
        # 停止要請でバックオフの待ちを打ち切り、残りの試行も行わない。
        sleep=stop_event.wait,
        should_stop=stop_event.is_set,
    )
    workers = SummaryWorkerPool(
        concurrency=config.concurrency,
        requests=requests,
        processor=processor,
        rescanner=rescanner,
        stop_event=stop_event,
    )
    return Summarization(config=config, requests=requests, rescanner=rescanner, workers=workers)
