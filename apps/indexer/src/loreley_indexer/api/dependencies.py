"""api 層が使う、担当機能の入口(module 4.1 の担当表)。`main.py` が組み立てて渡す。"""

from dataclasses import dataclass

from loreley_indexer.crawl_runs import CrawlRuns, DeletionManager
from loreley_indexer.documents import DocumentRegistrar, LastSeenUpdater


@dataclass(frozen=True)
class ApiDependencies:
    crawl_runs: CrawlRuns  # 開始通知・終了通知・Status
    deletion: DeletionManager  # ソース削除 1〜3
    registrar: DocumentRegistrar  # バッチ登録
    last_seen: LastSeenUpdater  # `last-seen`
