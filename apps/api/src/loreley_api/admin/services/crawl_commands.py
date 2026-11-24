"""クロールの起動・ジョブの取消・ロックの解放(EP-06・07・08。C 4章。D 5.1・5.2)。

入力は、ルーターが検証した ID と真偽値だけ。業務の判定(起動してよいか、取り消せるか、解放してよいか)
は Crawler が持つので、ここでは Crawler に 1 回だけ中継し、結果を写す。
"""

from functools import partial

from loreley_api.admin.base.errors import crawler_error
from loreley_api.admin.crawler_mapping import CrawlerOperation, RequestedOptions
from loreley_api.admin.schemas.common import JobAccepted
from loreley_api.admin.schemas.jobs import CancelJobResponse
from loreley_api.admin.schemas.sources import ReleaseLockResponse
from loreley_api.admin.services.crawler_relay import CrawlerRelay, WithStatus
from loreley_api.admin.services.crawler_responses import (
    to_cancel_job,
    to_job_accepted,
    to_release_lock,
)
from loreley_api.infrastructure.crawler_client import CrawlerClient


class CrawlCommandService:
    def __init__(self, *, crawler: CrawlerClient, relay: CrawlerRelay) -> None:
        self._crawler = crawler
        self._relay = relay

    async def start_crawl(
        self, source_id: str, *, force_delete: bool, rewrite_mode: bool
    ) -> JobAccepted:
        """EP-06。409 `lock_held` には、要求した指定を `requested` に載せる(B 2.7)。"""
        succeeded = await self._relay.send(
            CrawlerOperation.START_CRAWL,
            partial(
                self._crawler.start_crawl,
                source_id,
                force_delete=force_delete,
                rewrite_mode=rewrite_mode,
            ),
            lock_source_id=source_id,
            requested=RequestedOptions(force_delete=force_delete, rewrite_mode=rewrite_mode),
        )
        accepted = to_job_accepted(succeeded.body, has_options=True)
        if accepted is None:
            raise crawler_error()  # 受け付けたかもしれない(B 10.2)
        return accepted

    async def cancel(self, job_id: str) -> WithStatus[CancelJobResponse]:
        """EP-07。200(実行待ちを取り消した)または 202(実行中への取消要求の受付)。"""
        succeeded = await self._relay.send(
            CrawlerOperation.CANCEL_JOB, partial(self._crawler.cancel_job, job_id)
        )
        cancelled = to_cancel_job(succeeded.body)
        if cancelled is None:
            raise crawler_error()  # 取り消したかもしれない(B 10.2)
        return WithStatus(succeeded.status, cancelled)

    async def release_lock(self, source_id: str) -> ReleaseLockResponse:
        """EP-08。設定がなくても解放できる(ソース削除の後に残ったロック)。"""
        succeeded = await self._relay.send(
            CrawlerOperation.RELEASE_LOCK,
            partial(self._crawler.release_lock, source_id),
            lock_source_id=source_id,
        )
        released = to_release_lock(succeeded.body)
        if released is None:
            raise crawler_error()  # 解放したかもしれない(B 10.2)
        return released
