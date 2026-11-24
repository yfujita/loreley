"""メタ情報(EP-14)。設定だけで応答し、他のコンポーネントを呼ばない。"""

import pytest

from loreley_api.admin.schemas.meta import MetaResponse
from tests.admin.factories import make_admin_dependencies
from tests.api_config import make_admin_settings
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.fakes.inline_runner import InlineRunner

pytestmark = pytest.mark.anyio


async def get_meta(
    readers: InMemoryReaders, *, cron_timezone: str | None, dashboards_url: str | None
) -> MetaResponse:
    settings = make_admin_settings(cron_timezone=cron_timezone, dashboards_url=dashboards_url)
    deps = make_admin_dependencies(readers, FixedClock(), InlineRunner(), settings)
    return await deps.meta.get_meta()


async def test_the_settings_are_returned_as_they_are(readers: InMemoryReaders) -> None:
    response = await get_meta(
        readers, cron_timezone="Asia/Tokyo", dashboards_url="http://localhost:5601"
    )

    assert response.model_dump() == {
        "cron_timezone": "Asia/Tokyo",
        "dashboards_url": "http://localhost:5601",
    }


async def test_unset_values_are_null_not_utc(readers: InMemoryReaders) -> None:
    """未設定の `cron_timezone` を UTC とはみなさない(B 8.2)。"""
    response = await get_meta(readers, cron_timezone=None, dashboards_url=None)

    assert response.model_dump() == {"cron_timezone": None, "dashboards_url": None}


async def test_no_other_component_is_called(readers: InMemoryReaders) -> None:
    await get_meta(readers, cron_timezone="UTC", dashboards_url=None)

    assert readers.behavior.calls == []
