"""許可リストの OpenSearch クライアント(C 2.3。D 4.8 の 1 層目)。

生の `opensearchpy.OpenSearch` を包み、公開メソッドを次の 7 つに固定する。生のクライアントの
呼び先は、最後の属性名だけでなく**名前空間つき**で数える。

| 公開メソッド | 生のクライアントの呼び先 |
| --- | --- |
| `search` | `search` |
| `msearch` | `msearch` |
| `mget` | `mget` |
| `cluster_health` | `cluster.health` |
| `cat_indices` | `cat.indices` |
| `cat_shards` | `cat.shards` |
| `cat_nodes` | `cat.nodes` |

- 引数は明示のものだけ受ける。`**kwargs`・`**params` を生のクライアントへ素通ししない(許可した
  API に任意の引数を渡せないようにする)。`cat.*` の引数は固定(C 3.4)。
- 書き込み・索引管理・`refresh`・`scroll`・PIT・スクリプトに当たるメソッドを持たない。
  生のクライアントを返すメソッドもない。
- 応答は検証せずに返す(HTTP 200 の部分的な失敗の確認は Reader の責務。C 3.2)。

生のクライアントを呼んでよい場所は、このファイルだけ(D 6章 R8。`tests/architecture` が検査する)。
"""

from collections.abc import Mapping, Sequence

from opensearchpy import OpenSearch

from loreley_api.infrastructure.opensearch.queries import (
    CAT_INDICES_COLUMNS,
    CAT_NODES_COLUMNS,
    CAT_SHARDS_COLUMNS,
)


class ReadOnlyOpenSearch:
    def __init__(self, raw_client: OpenSearch) -> None:
        self._raw_client = raw_client

    def search(self, *, index: str, body: Mapping[str, object]) -> object:
        return self._raw_client.search(index=index, body=body)

    def msearch(self, *, body: Sequence[Mapping[str, object]]) -> object:
        """`body` は、サブ要求ごとの「ヘッダ(`index`)、本文」の繰り返し。"""
        return self._raw_client.msearch(body=body)

    def mget(
        self,
        *,
        index: str,
        ids: Sequence[str],
        source_includes: Sequence[str] | None = None,
        include_source: bool = True,
    ) -> object:
        """ID で取得する(ID は本文に載せる。パスに埋めない。C 3.2)。

        `include_source=False` は存在確認だけ(`_source` を返さない)。`source_includes` が
        `None` なら全項目。
        """
        body = {"ids": list(ids)}
        if not include_source:
            return self._raw_client.mget(index=index, body=body, _source=False)
        if source_includes is None:
            return self._raw_client.mget(index=index, body=body)
        return self._raw_client.mget(index=index, body=body, _source_includes=list(source_includes))

    def cluster_health(self) -> object:
        return self._raw_client.cluster.health()

    def cat_indices(self) -> object:
        # `expand_wildcards=all` は、クローズ済み・隠しインデックスも含めて抜けを出さないため。
        return self._raw_client.cat.indices(
            format="json", h=",".join(CAT_INDICES_COLUMNS), bytes="b", expand_wildcards="all"
        )

    def cat_shards(self) -> object:
        return self._raw_client.cat.shards(format="json", h=",".join(CAT_SHARDS_COLUMNS), bytes="b")

    def cat_nodes(self) -> object:
        return self._raw_client.cat.nodes(format="json", h=",".join(CAT_NODES_COLUMNS), bytes="b")
