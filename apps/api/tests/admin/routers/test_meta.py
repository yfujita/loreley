"""EP-14 `GET /meta`(アプリ全体)。"""

from fastapi.testclient import TestClient

from loreley_api.admin import create_admin_app
from loreley_api.server import SubAppMount, create_app
from tests.admin.factories import ADMIN_PREFIX, make_admin_dependencies
from tests.api_config import make_admin_settings
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.fakes.inline_runner import InlineRunner

META = f"{ADMIN_PREFIX}/meta"


def make_client(**settings: object) -> tuple[TestClient, InMemoryReaders]:
    readers = InMemoryReaders()
    deps = make_admin_dependencies(
        readers, FixedClock(), InlineRunner(), make_admin_settings(**settings)
    )
    app = create_app(mounts=[SubAppMount(ADMIN_PREFIX, create_admin_app(deps))])
    return TestClient(app), readers


def test_the_configured_values_are_returned() -> None:
    client, _ = make_client(cron_timezone="Asia/Tokyo", dashboards_url="http://localhost:5601")

    response = client.get(META)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "cron_timezone": "Asia/Tokyo",
        "dashboards_url": "http://localhost:5601",
    }


def test_unset_values_are_null_and_the_keys_stay() -> None:
    client, _ = make_client(cron_timezone=None, dashboards_url=None)

    assert client.get(META).json() == {"cron_timezone": None, "dashboards_url": None}


def test_no_other_component_is_called() -> None:
    client, readers = make_client()

    client.get(META)

    assert readers.behavior.calls == []


def test_an_unknown_query_is_a_400() -> None:
    client, _ = make_client()

    response = client.get(f"{META}?x=1")

    assert response.status_code == 400
    assert response.json()["error"]["details"]["errors"] == [
        {"field": "x", "reason": "unknown_field"}
    ]
