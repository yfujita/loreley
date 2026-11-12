"""クロール実行の状態管理(module 4.2)。`loreley-deletions` の読み書きの窓口。

- 開始通知・終了通知の受理、世代、Status、起動時の整理
- 登録の受理条件の照会(`documents` が使う。読み取りのみ)
- 終端状態への遷移と保持件数の整理(`deletion/` もここを経由する。R5)
"""

from loreley_indexer.crawl_runs.lifecycle.admission import Admission, AdmissionChecker
from loreley_indexer.crawl_runs.lifecycle.config import LifecycleConfig
from loreley_indexer.crawl_runs.lifecycle.finish import FinishReceiver
from loreley_indexer.crawl_runs.lifecycle.notifications import (
    FinishNotification,
    StartNotification,
)
from loreley_indexer.crawl_runs.lifecycle.records import (
    DeletionReason,
    DeletionRecord,
    DeletionResultRecord,
    DeletionStatus,
    FinishOutcome,
    MalformedRecordError,
    deletion_record_id,
    deletion_result_record_id,
)
from loreley_indexer.crawl_runs.lifecycle.restart import RestartCleaner
from loreley_indexer.crawl_runs.lifecycle.results import (
    ConditionalWrite,
    DeletionResults,
    StoredGeneration,
    StoredResult,
    retry_after_conflict,
)
from loreley_indexer.crawl_runs.lifecycle.start import CrawlStarter
from loreley_indexer.crawl_runs.lifecycle.status import CrawlStatus, StatusReader

__all__ = [
    "Admission",
    "AdmissionChecker",
    "ConditionalWrite",
    "CrawlStarter",
    "CrawlStatus",
    "DeletionReason",
    "DeletionRecord",
    "DeletionResultRecord",
    "DeletionResults",
    "DeletionStatus",
    "FinishNotification",
    "FinishOutcome",
    "FinishReceiver",
    "LifecycleConfig",
    "MalformedRecordError",
    "RestartCleaner",
    "StartNotification",
    "StatusReader",
    "StoredGeneration",
    "StoredResult",
    "deletion_record_id",
    "deletion_result_record_id",
    "retry_after_conflict",
]
