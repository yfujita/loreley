"""要約の生成・書き戻し・再走査(module 4.3、M-9)。

LLM を呼べるのはこのモジュールだけ(R9、M-11)。既定は無効。
"""

from loreley_indexer.documents.summarization.config import SummarizationConfig
from loreley_indexer.documents.summarization.processor import SummaryProcessor
from loreley_indexer.documents.summarization.request_queue import SubmitResult, SummaryRequestQueue
from loreley_indexer.documents.summarization.rescanner import SummaryRescanner
from loreley_indexer.documents.summarization.service import Summarization, create_summarization
from loreley_indexer.documents.summarization.status import SummaryOutcome, SummaryStatus
from loreley_indexer.documents.summarization.worker import SummaryWorkerPool

__all__ = [
    "SubmitResult",
    "Summarization",
    "SummarizationConfig",
    "SummaryOutcome",
    "SummaryProcessor",
    "SummaryRequestQueue",
    "SummaryRescanner",
    "SummaryStatus",
    "SummaryWorkerPool",
    "create_summarization",
]
