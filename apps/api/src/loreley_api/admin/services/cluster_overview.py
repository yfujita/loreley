"""OpenSearch の状態(EP-12。C 3.4。D 5.6)。

`cluster.health` と `cat.*` を、1 カード分の 1 つの取得結果として扱う。どれかが失敗した、または
応答が期待の形でなければ、部分的な応答にせず 503(B 7.1)。
"""

import logging

from loreley_api.admin.base.errors import unavailable
from loreley_api.admin.derivation.cluster_view import ClusterShapeError, normalize_cluster
from loreley_api.admin.schemas.opensearch import (
    ClusterResponse,
    ClusterSummary,
    IndexEntry,
    NodeEntry,
    ShardEntry,
)
from loreley_api.common.clock import Clock
from loreley_api.common.concurrency import CATEGORY_OPENSEARCH, BlockingRunner
from loreley_api.common.results import Failed
from loreley_api.infrastructure.opensearch import ClusterReader

logger = logging.getLogger(__name__)


class ClusterOverviewService:
    def __init__(self, *, cluster: ClusterReader, runner: BlockingRunner, clock: Clock) -> None:
        self._cluster = cluster
        self._runner = runner
        self._clock = clock

    async def get_cluster(self) -> ClusterResponse:
        now = self._clock.now()
        result = await self._runner.run(CATEGORY_OPENSEARCH, self._cluster.read)
        if isinstance(result, Failed):
            raise unavailable()

        snapshot = result.value
        try:
            view = normalize_cluster(
                snapshot.health, snapshot.indices, snapshot.shards, snapshot.nodes, now=now
            )
        except ClusterShapeError as error:
            # 応答の値は出さない(クラス名と固定の理由名だけ)。
            logger.error(
                "opensearch cluster response has an unexpected shape: error=%s reason=%s",
                type(error).__name__,
                error.reason,
            )
            raise unavailable() from None

        return ClusterResponse(
            fetched_at=view.fetched_at,
            cluster=ClusterSummary.model_validate(view.cluster, from_attributes=True),
            nodes=[NodeEntry(name=name) for name in view.nodes],
            indices=[IndexEntry.model_validate(i, from_attributes=True) for i in view.indices],
            shards=[ShardEntry.model_validate(s, from_attributes=True) for s in view.shards],
            truncated=view.truncated,
            total_indices=view.total_indices,
        )
