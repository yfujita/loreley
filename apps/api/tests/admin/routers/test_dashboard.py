"""EP-13 `GET /dashboard`(アプリ全体。B 8.1。C 11章 10)。

偽のプローブ・`InlineRunner` で、応答の形・順序・状態値・メソッド・入力の扱いを確かめる。
実クライアント(ローカル HTTP スタブ)を通した確認は `test_dashboard_over_http.py`。
"""

import pytest
from fastapi.testclient import TestClient

from loreley_api.admin import create_admin_app
from loreley_api.common.probe_outcome import ProbeOutcome
from loreley_api.server import SubAppMount, create_app
from tests.admin.factories import ADMIN_PREFIX, make_admin_dependencies
from tests.api_config import make_admin_settings
from tests.fakes.clock import FixedClock
from tests.fakes.fake_probes import FakeProbes
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.fakes.inline_runner import InlineRunner

DASHBOARD = f"{ADMIN_PREFIX}/dashboard"
CRAWLER_URL = "http://crawler.invalid:8001"
INDEXER_URL = "http://indexer.invalid:8000"
CONFIGURED_URLS = [f"{CRAWLER_URL}/healthz", f"{INDEXER_URL}/healthz"]
COMPONENT_KEYS = {"id", "state", "reason", "checked_at"}


def make_client(probes: FakeProbes, **settings: object) -> TestClient:
    deps = make_admin_dependencies(
        InMemoryReaders(),
        FixedClock(),
        InlineRunner(),
        make_admin_settings(crawler_url=CRAWLER_URL, indexer_url=INDEXER_URL, **settings),
        probes=probes.as_admin_probes(),
    )
    return TestClient(create_app(mounts=[SubAppMount(ADMIN_PREFIX, create_admin_app(deps))]))


def test_the_response_is_the_documented_shape_with_eight_components_in_order() -> None:
    probes = FakeProbes()
    probes.http.behavior.inject(
        "check", ProbeOutcome("abnormal", "connection_refused"), key=f"{INDEXER_URL}/healthz"
    )

    response = make_client(probes, llm_health_url="https://llm.invalid/healthz").get(DASHBOARD)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"checked_at", "components"}  # `unavailable` もエラーもない
    assert body["checked_at"] == "2026-11-24T00:00:00.000Z"
    assert all(set(component) == COMPONENT_KEYS for component in body["components"])
    assert [(c["id"], c["state"], c["reason"], c["checked_at"]) for c in body["components"]] == [
        ("crawler", "normal", None, "2026-11-24T00:00:00.000Z"),
        ("indexer", "abnormal", "connection_refused", "2026-11-24T00:00:00.000Z"),
        ("opensearch", "normal", None, "2026-11-24T00:00:00.000Z"),
        ("api", "normal", None, "2026-11-24T00:00:00.000Z"),
        ("web", "normal", None, "2026-11-24T00:00:00.000Z"),
        ("opensearch-dashboards", "not_configured", None, "2026-11-24T00:00:00.000Z"),
        ("embedding", "not_configured", None, "2026-11-24T00:00:00.000Z"),
        ("llm", "normal", None, "2026-11-24T00:00:00.000Z"),
    ]


@pytest.mark.parametrize(
    "outcome",
    [
        ProbeOutcome("normal"),
        ProbeOutcome("abnormal", "connection_refused"),
        ProbeOutcome("abnormal", "name_not_resolved"),
        ProbeOutcome("abnormal", "unexpected_status"),
        ProbeOutcome("abnormal", "missing"),
        ProbeOutcome("undetermined", "timeout"),
        ProbeOutcome("undetermined", "connection_error"),
    ],
)
def test_every_state_and_reason_value_is_returned_as_the_documented_string(
    outcome: ProbeOutcome,
) -> None:
    probes = FakeProbes()
    probes.opensearch.behavior.inject("check", outcome)

    body = make_client(probes).get(DASHBOARD).json()

    [opensearch] = [c for c in body["components"] if c["id"] == "opensearch"]
    assert (opensearch["state"], opensearch["reason"]) == (outcome.state, outcome.reason)


def test_the_state_of_one_component_failing_does_not_fail_the_response() -> None:
    probes = FakeProbes()
    down = ProbeOutcome("abnormal", "connection_refused")
    probes.http.behavior.inject("check", down, times=None)
    probes.opensearch.behavior.inject("check", down, times=None)

    response = make_client(probes).get(DASHBOARD)

    assert response.status_code == 200
    states = {c["id"]: c["state"] for c in response.json()["components"]}
    assert states["api"] == "normal"
    assert states["crawler"] == states["indexer"] == states["opensearch"] == "abnormal"


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_only_get_is_accepted(method: str) -> None:
    probes = FakeProbes()

    response = getattr(make_client(probes), method)(DASHBOARD)

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert probes.http.checked == []  # 確認は走らない


def test_an_unknown_query_is_a_400_and_nothing_is_probed() -> None:
    probes = FakeProbes()

    response = make_client(probes).get(f"{DASHBOARD}?url=http://evil.invalid/")

    assert response.status_code == 400
    assert response.json()["error"]["details"]["errors"] == [
        {"field": "url", "reason": "unknown_field"}
    ]
    assert (probes.http.checked, probes.opensearch.checked, probes.web_dist.checked) == ([], [], [])


@pytest.mark.parametrize(
    "path",
    [
        f"{DASHBOARD}/http://evil.invalid/",
        f"{DASHBOARD}/crawler",
        f"{DASHBOARD}/..%2Fmeta",
    ],
)
def test_a_path_under_the_dashboard_is_not_found_and_nothing_is_probed(path: str) -> None:
    probes = FakeProbes()

    response = make_client(probes).get(path)

    assert response.status_code == 404
    assert probes.http.checked == []


def test_the_probe_targets_come_only_from_the_settings_whatever_the_request_carries() -> None:
    """確認先を決める入力が、リクエストに存在しない(SSRF の経路がない。C 6.4)。"""
    probes = FakeProbes()
    client = make_client(probes)
    client.cookies.set("url", "http://evil.invalid/")

    client.get(
        DASHBOARD,
        headers={
            "Host": "evil.invalid",
            "X-Forwarded-Host": "evil.invalid",
            "X-Forwarded-For": "10.0.0.1",
            "Origin": "http://evil.invalid",
            "Referer": "http://evil.invalid/",
            "Forwarded": "host=evil.invalid",
            "X-Original-URL": "http://evil.invalid/",
        },
    )

    assert probes.http.checked == CONFIGURED_URLS
    assert probes.web_dist.checked == ["/nonexistent/web"]
    assert probes.opensearch.checked == [""]


def test_a_request_body_does_not_change_the_probe_targets() -> None:
    probes = FakeProbes()

    response = make_client(probes).request(
        "GET", DASHBOARD, json={"url": "http://evil.invalid/", "crawler_url": "http://evil.invalid"}
    )

    assert response.status_code == 200
    assert probes.http.checked == CONFIGURED_URLS
