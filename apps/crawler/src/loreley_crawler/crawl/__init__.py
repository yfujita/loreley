"""クロールジョブの実行(module 4.5。architecture 4.5〜4.8・6章・7章)。

入口は `CrawlExecutor`(Job Runner が呼ぶ実行対象。`main.py` が `CrawlDependencies` で組み立てる)。
`CrawlExecutor.__call__` は、実行開始から最終状態の記録まで(終了通知・ポーリング・異常系の最終対応を
含む)を行う。実行開始から終了通知の手前まで(列挙・登録・整理)だけを実行するテスト用の入口が
`run_until_finish_notice`。

状態・結果の型: `CrawlRun`(列挙・集計・ID 集合・警告・識別子エラーの例)、`RegistrationTally`、
`SettingsSnapshot`、`CrawlFailure`(理由コードと説明)、
`FinishNotice`、`PollingResult`・`DeletionConfirmation`。
"""

from loreley_crawler.crawl.dependencies import CrawlDependencies
from loreley_crawler.crawl.executor import CrawlExecutor
from loreley_crawler.crawl.failure import CrawlFailure
from loreley_crawler.crawl.finish_notice import FinishNotice
from loreley_crawler.crawl.run import CrawlRun
from loreley_crawler.crawl.settings import CrawlSettings
from loreley_crawler.crawl.skip_counter import ConsecutiveSkipCounter
from loreley_crawler.crawl.snapshot import SettingsSnapshot
from loreley_crawler.crawl.start import PreparedCrawl
from loreley_crawler.crawl.status_polling import DeletionConfirmation, PollingResult
from loreley_crawler.crawl.tally import RegistrationTally

__all__ = [
    "ConsecutiveSkipCounter",
    "CrawlDependencies",
    "CrawlExecutor",
    "CrawlFailure",
    "CrawlRun",
    "CrawlSettings",
    "DeletionConfirmation",
    "FinishNotice",
    "PollingResult",
    "PreparedCrawl",
    "RegistrationTally",
    "SettingsSnapshot",
]
