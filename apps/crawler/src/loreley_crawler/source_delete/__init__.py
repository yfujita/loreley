"""ソース削除ジョブの実行(module 4.6。architecture 8章)。

入口は `SourceDeleteExecutor`(Job Runner が呼ぶ実行対象。`main.py` が `SourceDeleteDependencies` で
組み立てる)。`__call__` は、実行開始(順 0)から最終状態の記録(順 6)までを行う。
"""

from loreley_crawler.source_delete.dependencies import SourceDeleteDependencies
from loreley_crawler.source_delete.executor import SourceDeleteExecutor
from loreley_crawler.source_delete.failure import SourceDeleteFailure

__all__ = ["SourceDeleteDependencies", "SourceDeleteExecutor", "SourceDeleteFailure"]
