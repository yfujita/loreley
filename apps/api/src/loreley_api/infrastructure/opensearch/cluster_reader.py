"""クラスタ情報の読み取り(R-12。`cluster.health`・`cat.*`。C 3.4)。

逐次に呼び、最初の失敗で打ち切る(どれかが失敗したら全体が失敗。B 7.1)。値は応答のまま返し、
正規化(整数・小文字・`prirep` の言い換え・補完・並べ替え・切り詰め)は `derivation` が行う。
応答が期待の形でない(必須の項目がない・型が違う)ときは失敗にする。
"""

from collections.abc import Sequence

from loreley_api.common.results import Result
from loreley_api.infrastructure.opensearch import queries
from loreley_api.infrastructure.opensearch.failure import ResponseShapeError, guarded_read
from loreley_api.infrastructure.opensearch.ports import ClusterSnapshot, Source
from loreley_api.infrastructure.opensearch.readonly_client import ReadOnlyOpenSearch
from loreley_api.infrastructure.opensearch.responses import as_list, as_mapping


class OpenSearchClusterReader:
    def __init__(self, readonly: ReadOnlyOpenSearch) -> None:
        self._readonly = readonly

    def read(self) -> Result[ClusterSnapshot]:
        # クラスタ情報は `loreley-*` でも検索インデックスでもないので、`Failed` の対象は `store`
        # とする(EP-12 は失敗を理由コードにせず、全体を 503 にするだけ。C 5.8)。
        return guarded_read("cluster.read", "store", self._read)

    def _read(self) -> ClusterSnapshot:
        health = _require_keys(
            as_mapping(self._readonly.cluster_health()), queries.CLUSTER_HEALTH_FIELDS
        )
        indices = _rows(self._readonly.cat_indices(), queries.CAT_INDICES_COLUMNS)
        shards = _rows(self._readonly.cat_shards(), queries.CAT_SHARDS_COLUMNS)
        nodes = _rows(self._readonly.cat_nodes(), queries.CAT_NODES_COLUMNS)
        return ClusterSnapshot(health=health, indices=indices, shards=shards, nodes=nodes)


def _rows(response: object, columns: Sequence[str]) -> tuple[Source, ...]:
    return tuple(_require_keys(as_mapping(row), columns) for row in as_list(response))


def _require_keys(value: Source, keys: Sequence[str]) -> Source:
    if any(key not in value for key in keys):
        raise ResponseShapeError("a required field is missing")
    return value
