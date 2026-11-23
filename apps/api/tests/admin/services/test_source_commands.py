"""データソースの登録・更新・削除ジョブの起動(EP-03・04・05)のサービス。

入力の検証・単位の換算・Crawler の応答の DTO 化。EP を通した確認は `routers/` にある。
"""

from typing import Any

import pytest

from loreley_api.admin.base.errors import AdminApiError
from loreley_api.admin.schemas.sources import RegisterSourceBody, UpdateSourceBody
from loreley_api.admin.services.source_commands import SourceCommandService
from loreley_api.infrastructure.crawler_client import CrawlerRejected, CrawlerSucceeded
from tests.admin.factories import make_admin_dependencies
from tests.admin.write_requests import crawler_source_body, register_body, update_body
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
) -> SourceCommandService:
    return make_admin_dependencies(
        readers, fixed_clock, inline_runner, crawler=crawler
    ).source_commands


async def test_a_registration_returns_the_status_of_the_crawler_and_the_settings_in_response_units(
    service: SourceCommandService, crawler: FakeCrawlerClient
) -> None:
    crawler.behavior.inject(
        "register_source",
        CrawlerSucceeded(200, crawler_source_body(ttl=86_400 * 7, ratio_threshold=0.125)),
    )

    written = await service.register(RegisterSourceBody.model_validate(register_body()))

    assert written.status_code == 200
    assert written.body.ttl_seconds == 86_400 * 7
    assert written.body.ttl_days == 7
    assert written.body.ratio_threshold_percent == 12.5
    assert written.body.schedule_cron == "0 3 * * *"


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"ttl_days": ..., "ttl_seconds": ...}, [("ttl_days", "required")]),
        ({"ttl_seconds": 1}, [("ttl_days", "exclusive")]),
        ({"ttl_days": 0}, [("ttl_days", "range")]),
        ({"ratio_threshold_percent": 100.0}, [("ratio_threshold_percent", "range")]),
        ({"ratio_threshold_percent": 0.005}, [("ratio_threshold_percent", "format")]),
        ({"min_delete_count": -1}, [("min_delete_count", "range")]),
        (
            {"ttl_days": 0, "ratio_threshold_percent": -1, "min_delete_count": -1},
            [
                ("ttl_days", "range"),
                ("ratio_threshold_percent", "range"),
                ("min_delete_count", "range"),
            ],
        ),
    ],
)
async def test_an_invalid_value_is_a_400_with_every_violation_and_is_not_sent(
    service: SourceCommandService,
    crawler: FakeCrawlerClient,
    change: dict[str, Any],
    expected: list[tuple[str, str]],
) -> None:
    body = UpdateSourceBody.model_validate(update_body(**change))

    with pytest.raises(AdminApiError) as raised:
        await service.update("docs", body)

    assert raised.value.status_code == 400
    assert raised.value.details is not None
    assert [(e["field"], e["reason"]) for e in raised.value.details["errors"]] == expected
    assert crawler.requests == []


async def test_a_delete_job_has_no_options_and_the_lock_conflict_has_no_requested(
    service: SourceCommandService, crawler: FakeCrawlerClient
) -> None:
    accepted = await service.start_delete("docs")
    crawler.behavior.inject(
        "start_delete_job",
        CrawlerRejected(409, "lock_held", {"existing_job": {"job_id": "j"}}, None),
    )

    with pytest.raises(AdminApiError) as raised:
        await service.start_delete("docs")

    assert (accepted.job_type.value, accepted.force_delete, accepted.rewrite_mode) == (
        "source_delete",
        None,
        None,
    )
    assert raised.value.details is not None
    assert set(raised.value.details) == {"existing_job", "lock_state"}
