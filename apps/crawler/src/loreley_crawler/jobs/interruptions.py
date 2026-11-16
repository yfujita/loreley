"""確認点(`JobContext`)が実行対象に知らせる中断(module 4.4。architecture 4.7・5.7・7.9)。

取り消し・所有権の喪失・メンテナンスは、それぞれの例外で知らせる。どう終えるか(`cancelled` か
`failed` か、終了通知を送るか)は実行対象が決める。メッセージ・`reason` は固定の短い文字列で、
識別子や本文を入れない(R11)。
"""

from loreley_crawler.common.errors import CrawlerError
from loreley_crawler.jobs.records import JobStatus


class JobInterrupted(CrawlerError):
    """確認点が、実行を続けてはならないと知らせた。"""


class CancellationRequested(JobInterrupted):
    """取り消し要求が届いている(architecture 4.7)。"""

    def __init__(self) -> None:
        super().__init__("cancellation requested")


class OwnershipLost(JobInterrupted):
    """ロックの所有権を失った(ハートビートの喪失、`lock_not_owned`、リース切れ。architecture 5.7)。

    `reason` は喪失の理由(`lock_missing`・`lock_taken_over`・`lease_expired`・`lock_not_owned`・
    `job_record_superseded` など。固定の名前)。
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class MaintenanceDetected(JobInterrupted):
    """メンテナンスフラグが立っている(architecture 7.9。fail-closed の判定を含む)。"""

    def __init__(self) -> None:
        super().__init__("maintenance flag is raised")


class JobNotStartable(CrawlerError):
    """`queued` -> `running` の条件付き更新に負けた。実行を始めてはならない。

    `status` は、読み直したジョブ記録の状態(記録がなければ None)。取り消しに負けたときは
    `cancelled`。実行対象は捕捉せずに伝播させる。Job Runner が、ロックを解放して止める
    (architecture 4.5 の手順 6・4.7)。
    """

    def __init__(self, status: JobStatus | None) -> None:
        super().__init__("the job cannot be started")
        self.status = status
