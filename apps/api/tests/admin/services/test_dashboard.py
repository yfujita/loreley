"""ダッシュボード(EP-13。C 6章・8.1。C 11章 10・14)。

`InlineRunner`(スレッドなし)で組み立てと分類・順序を確かめ、期限と並行は実物の `BlockingRunner` で
確かめる。確認先の URL は、設定から作った値だけ(リクエストから受け取らない)。
"""

import threading
import time

import anyio
import pytest

from loreley_api.admin.base.codes import ComponentId, ComponentState
from loreley_api.admin.schemas.dashboard import DashboardResponse
from loreley_api.admin.services.dashboard import DEADLINE_MARGIN_SECONDS, DashboardService
from loreley_api.common.concurrency import CATEGORY_PROBE, BlockingRunner
from loreley_api.common.probe_outcome import ProbeOutcome
from loreley_api.common.timestamps import format_instant
from tests.admin.factories import make_admin_dependencies
from tests.api_config import make_admin_settings
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.fake_probes import FakeProbes
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.fakes.inline_runner import InlineRunner
from tests.secret_assertions import assert_secret_absent
from tests.timing import TIMING_SLACK_SECONDS

pytestmark = pytest.mark.anyio

CRAWLER_URL = "http://crawler.invalid:8001"
INDEXER_URL = "http://indexer.invalid:8000"
WEB_URL = "http://web.invalid:80"
WEB_HEALTH_URL = f"{WEB_URL}/admin/"
DASHBOARDS_HEALTH_URL = "http://dashboards.invalid:5601/api/status"
EMBEDDING_HEALTH_URL = "http://embedding.invalid:8080/health"
LLM_HEALTH_URL = "https://llm.invalid/healthz"
NOW_TEXT = format_instant(DEFAULT_NOW)

ALL_IDS = [
    "crawler",
    "indexer",
    "opensearch",
    "api",
    "web",
    "opensearch-dashboards",
    "embedding",
    "llm",
]
OPTIONAL_URLS = {
    "dashboards_health_url": DASHBOARDS_HEALTH_URL,
    "embedding_health_url": EMBEDDING_HEALTH_URL,
    "llm_health_url": LLM_HEALTH_URL,
}


def make_service(
    probes: FakeProbes,
    runner: InlineRunner | BlockingRunner,
    clock: FixedClock | None = None,
    **settings: object,
) -> DashboardService:
    deps = make_admin_dependencies(
        InMemoryReaders(),
        clock if clock is not None else FixedClock(),
        runner,  # type: ignore[arg-type]
        make_admin_settings(
            crawler_url=CRAWLER_URL,
            indexer_url=INDEXER_URL,
            web_url=WEB_URL,
            **settings,
        ),
        probes=probes.as_admin_probes(),
    )
    return deps.dashboard


def summarize(response: DashboardResponse) -> list[tuple[str, str, str | None]]:
    return [(c.id, c.state, c.reason) for c in response.components]


async def test_the_components_are_always_eight_in_the_fixed_order() -> None:
    service = make_service(FakeProbes(), InlineRunner())

    response = await service.check_components()

    assert [component.id for component in response.components] == ALL_IDS
    assert [component.id for component in response.components] == list(ComponentId)


async def test_by_default_only_the_optional_components_are_not_configured() -> None:
    service = make_service(FakeProbes(), InlineRunner())

    response = await service.check_components()

    assert summarize(response) == [
        ("crawler", "normal", None),
        ("indexer", "normal", None),
        ("opensearch", "normal", None),
        ("api", "normal", None),
        ("web", "normal", None),
        ("opensearch-dashboards", "not_configured", None),
        ("embedding", "not_configured", None),
        ("llm", "not_configured", None),
    ]


@pytest.mark.parametrize(
    "configured",
    [
        pytest.param(["dashboards_health_url"], id="dashboards"),
        pytest.param(["embedding_health_url"], id="embedding"),
        pytest.param(["llm_health_url"], id="llm"),
        pytest.param(["dashboards_health_url", "llm_health_url"], id="dashboards and llm"),
        pytest.param(list(OPTIONAL_URLS), id="all three"),
    ],
)
async def test_an_optional_component_is_checked_only_when_its_url_is_configured(
    configured: list[str],
) -> None:
    probes = FakeProbes()
    service = make_service(
        probes, InlineRunner(), **{name: OPTIONAL_URLS[name] for name in configured}
    )

    response = await service.check_components()

    expected_by_setting = {
        "dashboards_health_url": ("opensearch-dashboards", DASHBOARDS_HEALTH_URL),
        "embedding_health_url": ("embedding", EMBEDDING_HEALTH_URL),
        "llm_health_url": ("llm", LLM_HEALTH_URL),
    }
    by_id = {component.id: component for component in response.components}
    for setting, (component_id, url) in expected_by_setting.items():
        if setting in configured:
            assert by_id[component_id].state == ComponentState.NORMAL
            assert url in probes.http.checked
        else:
            assert by_id[component_id].state == ComponentState.NOT_CONFIGURED
            assert by_id[component_id].reason is None
            assert url not in probes.http.checked


async def test_the_probed_urls_are_the_configured_ones_only() -> None:
    probes = FakeProbes()
    service = make_service(probes, InlineRunner(), **OPTIONAL_URLS)

    await service.check_components()

    assert probes.http.checked == [
        f"{CRAWLER_URL}/healthz",
        f"{INDEXER_URL}/healthz",
        WEB_HEALTH_URL,
        DASHBOARDS_HEALTH_URL,
        EMBEDDING_HEALTH_URL,
        LLM_HEALTH_URL,
    ]
    assert probes.opensearch.checked == [""]


@pytest.mark.parametrize(
    "outcome",
    [
        ProbeOutcome("abnormal", "connection_refused"),
        ProbeOutcome("abnormal", "name_not_resolved"),
        ProbeOutcome("abnormal", "unexpected_status"),
        ProbeOutcome("undetermined", "timeout"),
        ProbeOutcome("undetermined", "connection_error"),
    ],
)
@pytest.mark.parametrize(
    ("component_id", "url_key"),
    [
        ("crawler", f"{CRAWLER_URL}/healthz"),
        ("indexer", f"{INDEXER_URL}/healthz"),
        ("web", WEB_HEALTH_URL),
        ("opensearch-dashboards", DASHBOARDS_HEALTH_URL),
        ("embedding", EMBEDDING_HEALTH_URL),
        ("llm", LLM_HEALTH_URL),
    ],
)
async def test_the_outcome_of_a_probe_is_reported_for_that_component_only(
    component_id: str, url_key: str, outcome: ProbeOutcome
) -> None:
    probes = FakeProbes()
    probes.http.behavior.inject("check", outcome, key=url_key)
    service = make_service(probes, InlineRunner(), **OPTIONAL_URLS)

    response = await service.check_components()

    for component in response.components:
        if component.id == component_id:
            assert (component.state, component.reason) == (outcome.state, outcome.reason)
        else:
            assert component.state == ComponentState.NORMAL or (
                component.state == ComponentState.NOT_CONFIGURED
            )
            assert component.reason is None


async def test_the_opensearch_outcome_is_reported_as_the_opensearch_component() -> None:
    probes = FakeProbes()
    probes.opensearch.behavior.inject("check", ProbeOutcome("abnormal", "connection_refused"))
    service = make_service(probes, InlineRunner())

    response = await service.check_components()

    assert summarize(response)[:3] == [
        ("crawler", "normal", None),
        ("indexer", "normal", None),
        ("opensearch", "abnormal", "connection_refused"),
    ]


async def test_the_web_component_follows_the_probe_of_the_admin_path_of_the_web_url() -> None:
    probes = FakeProbes()
    probes.http.behavior.inject(
        "check", ProbeOutcome("abnormal", "connection_refused"), key=WEB_HEALTH_URL
    )
    service = make_service(probes, InlineRunner())

    response = await service.check_components()

    assert ("web", "abnormal", "connection_refused") in summarize(response)
    assert [component.state for component in response.components if component.id != "web"] == [
        "normal",
        "normal",
        "normal",
        "normal",
        "not_configured",
        "not_configured",
        "not_configured",
    ]


async def test_the_api_component_is_always_normal_even_when_everything_else_fails() -> None:
    probes = FakeProbes()
    down = ProbeOutcome("abnormal", "connection_refused")
    probes.http.behavior.inject("check", down, times=None)
    probes.opensearch.behavior.inject("check", down, times=None)
    service = make_service(probes, InlineRunner(), **OPTIONAL_URLS)

    response = await service.check_components()

    assert [(c.id, c.state) for c in response.components if c.id == "api"] == [("api", "normal")]
    assert all(c.state == ComponentState.ABNORMAL for c in response.components if c.id != "api")


async def test_the_probes_run_in_the_probe_category_with_the_deadline_of_timeout_plus_one() -> None:
    runner = InlineRunner()
    service = make_service(FakeProbes(), runner, probe_timeout_seconds=3.0, **OPTIONAL_URLS)

    await service.check_components()

    assert DEADLINE_MARGIN_SECONDS == 1.0
    assert runner.run_all_deadlines == [4.0]
    # crawler・indexer・opensearch・web と、設定された任意の 3 つ(`api` は確認しない)。
    assert runner.categories == [CATEGORY_PROBE] * 7


async def test_the_deadline_follows_the_configured_probe_timeout() -> None:
    runner = InlineRunner()
    service = make_service(FakeProbes(), runner, probe_timeout_seconds=0.5)

    await service.check_components()

    assert runner.run_all_deadlines == [1.5]


async def test_the_web_probe_goes_through_the_runner_like_the_other_http_probes() -> None:
    probes = FakeProbes()
    runner = InlineRunner()
    service = make_service(probes, runner)

    await service.check_components()

    assert probes.http.checked == [
        f"{CRAWLER_URL}/healthz",
        f"{INDEXER_URL}/healthz",
        WEB_HEALTH_URL,
    ]
    # 枠を通ったのは 4 つ(crawler・indexer・opensearch・web)。
    assert runner.categories == [CATEGORY_PROBE] * 4


# `InlineRunner` の `abandoned_indexes` は、`run_all` に渡された呼び出しの順(crawler・indexer・
# opensearch・web・設定された任意)の何番目かで指定する。
@pytest.mark.parametrize(
    ("index", "component_id"),
    [(0, "crawler"), (1, "indexer"), (2, "opensearch"), (3, "web")],
)
async def test_a_probe_that_passed_the_deadline_is_undetermined_timeout_and_the_others_are_kept(
    index: int, component_id: str
) -> None:
    runner = InlineRunner(abandoned_indexes={index})
    service = make_service(FakeProbes(), runner)

    response = await service.check_components()

    assert len(response.components) == 8
    for component in response.components:
        if component.id == component_id:
            assert (component.state, component.reason) == ("undetermined", "timeout")
        elif component.id in ("opensearch-dashboards", "embedding", "llm"):
            assert component.state == ComponentState.NOT_CONFIGURED
        else:
            assert (component.state, component.reason) == ("normal", None)


async def test_every_probe_that_passed_the_deadline_is_undetermined_timeout() -> None:
    runner = InlineRunner(abandoned_indexes={0, 1, 2, 3, 4, 5, 6})
    service = make_service(FakeProbes(), runner, **OPTIONAL_URLS)

    response = await service.check_components()

    assert summarize(response) == [
        ("crawler", "undetermined", "timeout"),
        ("indexer", "undetermined", "timeout"),
        ("opensearch", "undetermined", "timeout"),
        ("api", "normal", None),
        ("web", "undetermined", "timeout"),
        ("opensearch-dashboards", "undetermined", "timeout"),
        ("embedding", "undetermined", "timeout"),
        ("llm", "undetermined", "timeout"),
    ]


async def test_the_checked_at_of_a_component_is_when_its_probe_finished() -> None:
    """各 `components[].checked_at` はその確認が終わった時刻、トップは応答を組み立てた時刻。"""
    clock = FixedClock()
    probes = FakeProbes()
    # クロールの確認が終わるまでに 2 秒かかったことにする。
    probes.http.behavior.before(
        "check", lambda: clock.advance(seconds=2), key=f"{CRAWLER_URL}/healthz"
    )
    service = make_service(probes, InlineRunner(), clock)

    response = await service.check_components()

    by_id = {component.id: component for component in response.components}
    finished_at = format_instant(DEFAULT_NOW.replace(second=2))
    assert by_id["crawler"].checked_at == finished_at
    assert by_id["opensearch"].checked_at == finished_at  # 後に実行した確認
    assert response.checked_at >= max(component.checked_at for component in response.components)


async def test_a_component_that_passed_the_deadline_is_stamped_when_the_response_is_built() -> None:
    clock = FixedClock()
    probes = FakeProbes()
    probes.http.behavior.before("check", lambda: clock.advance(seconds=1))
    service = make_service(probes, InlineRunner(abandoned_indexes={2}), clock)

    response = await service.check_components()

    by_id = {component.id: component for component in response.components}
    assert by_id["opensearch"].checked_at == response.checked_at
    assert response.checked_at >= max(component.checked_at for component in response.components)


async def test_with_a_fixed_clock_the_top_level_and_every_component_checked_at_are_the_same() -> (
    None
):
    service = make_service(FakeProbes(), InlineRunner())

    response = await service.check_components()

    assert response.checked_at == NOW_TEXT
    assert {component.checked_at for component in response.components} == {NOW_TEXT}


async def test_a_not_configured_component_is_not_probed_and_has_no_reason() -> None:
    probes = FakeProbes()
    service = make_service(probes, InlineRunner())

    await service.check_components()

    assert len(probes.http.checked) == 3  # crawler・indexer・web だけ


# --- 実物の `BlockingRunner`(スレッド・期限・放棄) ---

PROBE_TIMEOUT_SECONDS = 0.2
# 期限(確認 + 1 秒)に、スレッドの起動・イベントループの揺れの余裕を足した、応答の所要時間の上限。
RESPONSE_LIMIT_SECONDS = PROBE_TIMEOUT_SECONDS + DEADLINE_MARGIN_SECONDS + TIMING_SLACK_SECONDS
# 期限より前に戻ることの確認に使う、遅くない確認の所要時間の上限。
PROMPT_SECONDS = 0.5


async def check_with_slow_probe(
    probes: FakeProbes, release: threading.Event, **settings: object
) -> tuple[DashboardResponse, float]:
    service = make_service(
        probes, BlockingRunner(), probe_timeout_seconds=PROBE_TIMEOUT_SECONDS, **settings
    )
    started_at = time.monotonic()
    try:
        response = await service.check_components()
    finally:
        elapsed = time.monotonic() - started_at
        release.set()  # 放棄したスレッドを終わらせる
    return response, elapsed


@pytest.mark.parametrize(
    ("slow_component", "probe_name", "key"),
    [
        ("crawler", "http", f"{CRAWLER_URL}/healthz"),
        ("indexer", "http", f"{INDEXER_URL}/healthz"),
        ("opensearch", "opensearch", None),
        ("web", "http", WEB_HEALTH_URL),
        ("opensearch-dashboards", "http", DASHBOARDS_HEALTH_URL),
        ("llm", "http", LLM_HEALTH_URL),
    ],
)
async def test_one_slow_probe_does_not_delay_the_others_and_the_response_is_within_the_deadline(
    slow_component: str, probe_name: str, key: str | None
) -> None:
    """C 11章 10・14: 1 つが遅くても他を待たせず、全体は期限(確認 + 1 秒)内に応答する。"""
    probes = FakeProbes()
    release = threading.Event()
    getattr(probes, probe_name).behavior.before("check", lambda: release.wait(30), key=key)

    response, elapsed = await check_with_slow_probe(
        probes, release, dashboards_health_url=DASHBOARDS_HEALTH_URL, llm_health_url=LLM_HEALTH_URL
    )

    assert elapsed < RESPONSE_LIMIT_SECONDS
    assert elapsed >= DEADLINE_MARGIN_SECONDS  # 期限まで待ってから、結果なしとして扱った
    for component in response.components:
        if component.id == slow_component:
            assert (component.state, component.reason) == ("undetermined", "timeout")
        elif component.id == "embedding":
            assert component.state == ComponentState.NOT_CONFIGURED
        else:
            assert (component.state, component.reason) == ("normal", None)
    assert len(response.components) == 8


async def test_without_a_slow_probe_the_response_does_not_wait_for_the_deadline() -> None:
    """遅い確認がなければ、(長い)期限を待たずに応答する。遅い確認があるときは、次のテスト。"""
    probes = FakeProbes()
    service = make_service(probes, BlockingRunner(), probe_timeout_seconds=30.0)

    started_at = time.monotonic()
    response = await service.check_components()

    assert time.monotonic() - started_at < PROMPT_SECONDS
    assert summarize(response)[0] == ("crawler", "normal", None)


async def test_several_slow_probes_are_all_cut_at_the_same_deadline() -> None:
    probes = FakeProbes()
    release = threading.Event()
    for url in (f"{CRAWLER_URL}/healthz", f"{INDEXER_URL}/healthz", WEB_HEALTH_URL):
        probes.http.behavior.before("check", lambda: release.wait(30), key=url)
    probes.opensearch.behavior.before("check", lambda: release.wait(30))

    response, elapsed = await check_with_slow_probe(probes, release)

    assert elapsed < RESPONSE_LIMIT_SECONDS
    assert summarize(response)[:5] == [
        ("crawler", "undetermined", "timeout"),
        ("indexer", "undetermined", "timeout"),
        ("opensearch", "undetermined", "timeout"),
        ("api", "normal", None),
        ("web", "undetermined", "timeout"),
    ]


async def test_the_event_loop_keeps_running_while_the_probes_wait() -> None:
    """待っている間、イベントループは塞がれない(他の EP・`/healthz` が応答できる)。"""
    probes = FakeProbes()
    release = threading.Event()
    probes.opensearch.behavior.before("check", lambda: release.wait(30))
    ticks = 0

    async def count_ticks() -> None:
        nonlocal ticks
        while True:
            await anyio.sleep(0.05)
            ticks += 1

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(count_ticks)
        _, _ = await check_with_slow_probe(probes, release)
        task_group.cancel_scope.cancel()

    assert ticks >= 5


async def test_the_urls_are_not_written_to_the_logs_when_a_probe_passes_the_deadline(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")
    secret_path = "SENTINEL-HEALTH-TOKEN"
    probes = FakeProbes()
    release = threading.Event()
    probes.http.behavior.before("check", lambda: release.wait(30))

    await check_with_slow_probe(
        probes, release, dashboards_health_url=f"http://dashboards.invalid/{secret_path}"
    )

    assert any("dashboard probe passed the deadline" in r.getMessage() for r in caplog.records)
    assert_secret_absent(secret_path, records=caplog.records)
    assert_secret_absent("crawler.invalid", records=caplog.records)
