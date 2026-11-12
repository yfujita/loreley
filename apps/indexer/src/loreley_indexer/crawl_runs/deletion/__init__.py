"""削除の判定・実行とソース削除(module 4.2 の `deletion/`)。

削除結果の状態の更新は `lifecycle/` に依頼する(R5: `deletion/` → `lifecycle/` の一方向)。
公開する入口は `DeletionManager`(`create_deletion_manager` で組み立てる)。
"""

from loreley_indexer.crawl_runs.deletion.config import DeletionConfig
from loreley_indexer.crawl_runs.deletion.outcome import DeletionOutcome
from loreley_indexer.crawl_runs.deletion.service import DeletionManager, create_deletion_manager

__all__ = [
    "DeletionConfig",
    "DeletionManager",
    "DeletionOutcome",
    "create_deletion_manager",
]
