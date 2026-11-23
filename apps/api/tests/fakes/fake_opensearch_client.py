"""生の OpenSearch クライアント(`opensearchpy.OpenSearch`)の偽物(D 7.2)。

`ReadOnlyOpenSearch` の下に置いて使う。許可リスト(`search`・`msearch`・`mget`・`cluster.health`・
`cat.indices`・`cat.shards`・`cat.nodes`)の外の呼び出し(`index`・`indices.*`・`scroll` など、
存在しない属性)は、`ForbiddenOpenSearchCall` で失敗する。

- 台本: `script(操作名, 応答または例外)`。呼び出しごとに 1 つ使い、台本がなければ
  `UnscriptedOpenSearchCall` で失敗する。操作名は名前空間つき(`cat.indices` など)。
- 記録: `requests` に、操作名・索引・本文・クエリ引数を残す(発行したクエリ本文の確認用)。

クエリの**意味**(フィルタ・集計・並べ替え)は実行しない。実 OpenSearch での確認は結合テストの範囲。

偽物の失敗は `BaseException` にしてある。Reader は `Exception` をすべて `Failed` にするので、
`Exception` の子にすると、テストの誤り(許可リスト外の呼び出し・台本の不足)が `Failed` に
変換されて見逃される(pytest の `Failed` と同じ理由)。
"""

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from tests.fakes.behavior import FakeBehavior


class ForbiddenOpenSearchCall(BaseException):
    """許可リストにない API を呼んだ。"""


class UnscriptedOpenSearchCall(BaseException):
    """台本にない呼び出しをした。"""


@dataclass(frozen=True)
class RecordedRequest:
    operation: str
    index: str | None
    body: object
    query_params: Mapping[str, object]


class _Namespace:
    """`cluster`・`cat` のように、許可した API だけを持つ名前空間。"""

    def __init__(self, name: str, apis: Mapping[str, Callable[..., object]]) -> None:
        self._name = name
        self._apis = dict(apis)

    def __getattr__(self, attribute: str) -> Callable[..., object]:
        try:
            return self._apis[attribute]
        except KeyError:
            raise ForbiddenOpenSearchCall(f"{self._name}.{attribute}") from None


class FakeOpenSearchClient:
    def __init__(self) -> None:
        self._behavior = FakeBehavior()
        self.requests: list[RecordedRequest] = []
        self.cluster = _Namespace("cluster", {"health": self._operation("cluster.health")})
        self.cat = _Namespace(
            "cat",
            {
                "indices": self._operation("cat.indices"),
                "shards": self._operation("cat.shards"),
                "nodes": self._operation("cat.nodes"),
            },
        )
        self.search = self._operation("search")
        self.msearch = self._operation("msearch")
        self.mget = self._operation("mget")
        self.close_count = 0

    def __getattr__(self, attribute: str) -> object:
        # 存在しない属性(`index`・`bulk`・`indices`・`scroll` ...)は、許可リスト外。
        raise ForbiddenOpenSearchCall(attribute)

    def close(self) -> None:
        self.close_count += 1

    def script(self, operation: str, outcome: object, *, times: int | None = 1) -> None:
        """次の `times` 回の `operation` の戻り値(例外なら送出する)を決める。"""
        self._behavior.inject(operation, outcome, times=times)

    def requests_of(self, operation: str) -> list[RecordedRequest]:
        return [request for request in self.requests if request.operation == operation]

    def _operation(self, operation: str) -> Callable[..., object]:
        def call(
            *,
            body: object = None,
            index: str | None = None,
            **query_params: object,
        ) -> object:
            self.requests.append(
                RecordedRequest(operation, index, copy.deepcopy(body), dict(query_params))
            )
            intercepted = self._behavior.enter(operation)
            if intercepted is None:
                raise UnscriptedOpenSearchCall(operation)
            return intercepted.value

        return call
