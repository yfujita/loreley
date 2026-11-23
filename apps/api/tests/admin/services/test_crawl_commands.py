"""クロールの起動・取消・ロックの解放(EP-06・07・08)のサービス。EP を通した確認は `routers/`。"""

import pytest

from loreley_api.admin.base.codes import JobStatus
from loreley_api.admin.base.errors import AdminApiError
from loreley_api.admin.services.crawl_commands import CrawlCommandService
from loreley_api.infrastructure.crawler_client import CrawlerRejected, CrawlerSucceeded
from tests.admin.factories import make_admin_dependencies
from tests.fakes.clock import FixedClock
from tests.fakes.fake_crawler_client import FakeCrawlerClient
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.fakes.inline_runner import InlineRunner

pytestmark = pytest.mark.anyio


@pytest.fixture
def service(
    readers: InMemoryReaders,
    fixed_clock: FixedClock,
    inline_runner: InlineRunner,
    crawler: FakeCrawlerClient,
) -> CrawlCommandService:
    return make_admin_dependencies(
        readers, fixed_clock, inline_runner, crawler=crawler
    ).crawl_commands


@pytest.mark.parametrize(("force_delete", "rewrite_mode"), [(True, False), (False, True)])
async def test_a_crawl_passes_both_options_by_name(
    service: CrawlCommandService,
    crawler: FakeCrawlerClient,
    force_delete: bool,
    rewrite_mode: bool,
) -> None:
    accepted = await service.start_crawl(
        "docs", force_delete=force_delete, rewrite_mode=rewrite_mode
    )

    assert crawler.requests[0].arguments == {
        "source_id": "docs",
        "force_delete": force_delete,
        "rewrite_mode": rewrite_mode,
    }
    assert (accepted.force_delete, accepted.rewrite_mode) == (force_delete, rewrite_mode)


async def test_a_crawl_conflict_carries_the_requested_options_and_says_they_were_not_applied(
    service: CrawlCommandService, crawler: FakeCrawlerClient
) -> None:
    crawler.behavior.inject(
        "start_crawl", CrawlerRejected(409, "lock_held", {"existing_job": {"job_id": "j"}}, None)
    )

    with pytest.raises(AdminApiError) as raised:
        await service.start_crawl("docs", force_delete=True, rewrite_mode=False)

    assert raised.value.details is not None
    assert raised.value.details["options_applied"] is False
    assert raised.value.details["requested"] == {"force_delete": True, "rewrite_mode": False}


async def test_a_cancel_returns_the_status_of_the_crawler(
    service: CrawlCommandService, crawler: FakeCrawlerClient
) -> None:
    crawler.behavior.inject(
        "cancel_job", CrawlerSucceeded(202, {"job_id": "job-1", "status": "running"})
    )

    cancelled = await service.cancel("job-1")

    assert cancelled.status_code == 202
    assert cancelled.body.status is JobStatus.RUNNING


async def test_a_lock_release_with_nothing_to_release_is_not_an_error(
    service: CrawlCommandService, crawler: FakeCrawlerClient
) -> None:
    crawler.behavior.inject(
        "release_lock",
        CrawlerSucceeded(200, {"source_id": "docs", "released": False, "failed_job_id": None}),
    )

    released = await service.release_lock("docs")

    assert (released.released, released.failed_job_id) == (False, None)
