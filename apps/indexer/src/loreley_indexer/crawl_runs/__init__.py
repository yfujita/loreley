"""クロール実行の状態管理と、削除の判断・実行(arch の Deletion Manager。module 4.2)。

documents に見せる入口(受理条件の照会)と、api に見せる入口(`CrawlRuns`、`DeletionManager`)を
ここに置く(R3: documents → crawl_runs は受理条件の照会だけ)。
"""

from loreley_indexer.crawl_runs.deletion import (
    DeletionConfig,
    DeletionManager,
    DeletionOutcome,
    create_deletion_manager,
)
from loreley_indexer.crawl_runs.lifecycle import (
    Admission,
    AdmissionChecker,
    CrawlStatus,
    FinishNotification,
    FinishOutcome,
    LifecycleConfig,
    StartNotification,
)
from loreley_indexer.crawl_runs.service import CrawlRuns

__all__ = [
    "Admission",
    "AdmissionChecker",
    "CrawlRuns",
    "CrawlStatus",
    "DeletionConfig",
    "DeletionManager",
    "DeletionOutcome",
    "FinishNotification",
    "FinishOutcome",
    "LifecycleConfig",
    "StartNotification",
    "create_deletion_manager",
]
