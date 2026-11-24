"""ダッシュボード(EP-13。C 6章。D 5.5)。

8 つのコンポーネントを固定の順で返す。`crawler`・`indexer`・`opensearch` と、設定された任意
コンポーネントの確認は、`probe` の枠で並行に実行し、全体の期限(確認のタイムアウト + 1 秒)で
打ち切る。期限までに終わらなかった確認は `undetermined`(`timeout`)にする。1 つが遅くても、
他を待たせず、全体は期限内に応答する。

- `api`: 応答できていること自体が根拠なので、常に `normal`。
- `web`: ローカルのファイルの確認だけなので、枠を通さずに直接呼ぶ(R9 の明示の例外)。
- 任意コンポーネント: 確認先の URL が未設定なら、確認せず `not_configured`。

確認先の URL は、設定(環境変数)から得た値だけを使う。リクエストからは何も受け取らない(C 6.4)。
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from loreley_api.admin.base.codes import ComponentId, ComponentState
from loreley_api.admin.schemas.dashboard import ComponentStatus, DashboardResponse
from loreley_api.common.clock import Clock
from loreley_api.common.concurrency import CATEGORY_PROBE, Abandoned, BlockingRunner
from loreley_api.common.probe_outcome import ProbeOutcome
from loreley_api.common.timestamps import format_instant
from loreley_api.infrastructure.opensearch import OpenSearchHealthCheck
from loreley_api.infrastructure.probes import HttpHealthCheck, WebDistCheck

logger = logging.getLogger(__name__)

# `crawler`・`indexer` の確認先(`{CRAWLER_URL}/healthz`)。任意コンポーネントは設定された完全な URL。
HEALTH_PATH = "/healthz"
# 全体の期限は、確認 1 件のタイムアウトにこの秒数を足した値(C 6.1)。
DEADLINE_MARGIN_SECONDS = 1.0

_ABANDONED_OUTCOME = ProbeOutcome("undetermined", "timeout")


@dataclass(frozen=True)
class _Finished:
    """確認の結果と、確認が終わった時刻(スレッドの中で時計を読む)。"""

    outcome: ProbeOutcome
    finished_at: datetime


class DashboardService:
    def __init__(
        self,
        *,
        http_probe: HttpHealthCheck,
        opensearch_probe: OpenSearchHealthCheck,
        web_probe: WebDistCheck,
        runner: BlockingRunner,
        clock: Clock,
        crawler_url: str,
        indexer_url: str,
        dashboards_health_url: str | None,
        embedding_health_url: str | None,
        llm_health_url: str | None,
        web_dist_dir: str,
        probe_timeout_seconds: float,
    ) -> None:
        self._http_probe = http_probe
        self._opensearch_probe = opensearch_probe
        self._web_probe = web_probe
        self._runner = runner
        self._clock = clock
        self._web_dist_dir = web_dist_dir
        self._deadline_seconds = probe_timeout_seconds + DEADLINE_MARGIN_SECONDS
        # 確認先の URL は、起動時に設定から作り、実行時には変えない。
        self._crawler_health_url = f"{crawler_url}{HEALTH_PATH}"
        self._indexer_health_url = f"{indexer_url}{HEALTH_PATH}"
        # 任意コンポーネントの確認先(完全な URL)。`None` は未設定。
        self._optional_health_urls: dict[ComponentId, str | None] = {
            ComponentId.OPENSEARCH_DASHBOARDS: dashboards_health_url,
            ComponentId.EMBEDDING: embedding_health_url,
            ComponentId.LLM: llm_health_url,
        }

    async def check_components(self) -> DashboardResponse:
        probe_calls = self._build_probe_calls()
        results = await self._runner.run_all(
            CATEGORY_PROBE, list(probe_calls.values()), self._deadline_seconds
        )

        statuses = {
            component_id: self._status_of_probed(component_id, finished)
            for component_id, finished in zip(probe_calls, results, strict=True)
        }
        statuses[ComponentId.API] = self._status(ComponentId.API, ProbeOutcome("normal"))
        # ローカルのファイルの確認だけなので、`runner` を通さずに直接呼ぶ(R9 の例外)。
        statuses[ComponentId.WEB] = self._status(
            ComponentId.WEB, self._web_probe.check(self._web_dist_dir)
        )
        for component_id, url in self._optional_health_urls.items():
            if url is None:
                statuses[component_id] = self._not_configured(component_id)

        return DashboardResponse(
            checked_at=format_instant(self._clock.now()),
            components=[statuses[component_id] for component_id in ComponentId],
        )

    def _build_probe_calls(self) -> dict[ComponentId, Callable[[], _Finished]]:
        """`probe` の枠で実行する確認。順は `crawler`・`indexer`・`opensearch`・設定された任意。"""
        calls = {
            ComponentId.CRAWLER: self._timed_http_check(self._crawler_health_url),
            ComponentId.INDEXER: self._timed_http_check(self._indexer_health_url),
            ComponentId.OPENSEARCH: self._timed(self._opensearch_probe.check),
        }
        for component_id, url in self._optional_health_urls.items():
            if url is not None:
                calls[component_id] = self._timed_http_check(url)
        return calls

    def _timed_http_check(self, url: str) -> Callable[[], _Finished]:
        return self._timed(lambda: self._http_probe.check(url))

    def _timed(self, probe: Callable[[], ProbeOutcome]) -> Callable[[], _Finished]:
        def run() -> _Finished:
            outcome = probe()
            return _Finished(outcome, self._clock.now())

        return run

    def _status_of_probed(
        self, component_id: ComponentId, finished: _Finished | Abandoned
    ) -> ComponentStatus:
        if isinstance(finished, Abandoned):
            # 確認が終わっていないので、`checked_at` は応答を組み立てる時刻にする。
            logger.warning("dashboard probe passed the deadline: component=%s", component_id.value)
            return self._status(component_id, _ABANDONED_OUTCOME)
        return self._status(component_id, finished.outcome, checked_at=finished.finished_at)

    def _status(
        self,
        component_id: ComponentId,
        outcome: ProbeOutcome,
        *,
        checked_at: datetime | None = None,
    ) -> ComponentStatus:
        return ComponentStatus(
            id=component_id,
            state=ComponentState(outcome.state),
            reason=outcome.reason,
            checked_at=format_instant(checked_at or self._clock.now()),
        )

    def _not_configured(self, component_id: ComponentId) -> ComponentStatus:
        return ComponentStatus(
            id=component_id,
            state=ComponentState.NOT_CONFIGURED,
            reason=None,
            checked_at=format_instant(self._clock.now()),
        )
