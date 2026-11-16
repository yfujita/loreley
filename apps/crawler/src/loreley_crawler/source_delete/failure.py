"""`source_delete` が理由コードを決めて、ジョブを `failed` にすべきと判断した失敗。"""

from loreley_crawler.common.errors import CrawlerError
from loreley_crawler.jobs import FailureReason


class SourceDeleteFailure(CrawlerError):
    """ジョブを `failed`(`reason`)にすべき失敗(architecture 4.8・8.1)。

    `detail` は `failure_detail` に書く固定文(保存の前に `JobContext.finish` が表示用に整形する)。
    Indexer のエラーメッセージ・リクエストの値は含めない(R11)。
    """

    def __init__(self, reason: FailureReason, detail: str) -> None:
        super().__init__(reason.value)
        self.reason = reason
        self.detail = detail
