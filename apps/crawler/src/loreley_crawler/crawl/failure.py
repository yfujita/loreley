"""`crawl` が理由コードを決めて、ジョブを `failed` にすべきと判断した失敗。"""

from loreley_crawler.common.errors import CrawlerError
from loreley_crawler.jobs import FailureReason


class CrawlFailure(CrawlerError):
    """ジョブを `failed`(`reason`)にすべき失敗(architecture 4.8)。

    `detail` は `failure_detail` に書く説明(保存の前に `JobContext.finish` が表示用に整形する)。
    本文・認証情報は含めない。例外のメッセージには理由コードだけを入れ、`detail`(外部由来の
    文字列を含みうる)はログに出さない。
    """

    def __init__(self, reason: FailureReason, detail: str | None = None) -> None:
        super().__init__(reason.value)
        self.reason = reason
        self.detail = detail
