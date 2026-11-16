"""OpenSearch の通信層(transport)の代わりになる、メモリ上のエミュレータ。

実際の `OpenSearch` クライアントの `transport` に差し替えて使う。クライアントが組み立てる
リクエスト(HTTP メソッド・パス・クエリパラメータ・本文)を解釈して、`OpenSearchRepository` を
メモリ上の記録に対して動かす。同じ契約テストを、これを使った `OpenSearchRepository` と、
`InMemoryRepository` の両方に流すためのもの
(tests/infrastructure/opensearch/test_repository_contract.py)。

OpenSearch の理解を再現したもので、実機と食い違う可能性がある(実 OpenSearch の統合テストで確認する。
architecture 12章 #37。CM-U-1、CA-U-18)。再現するもの:
- 取得はリアルタイム、検索は `_refresh` するまで書き込みが見えない(refresh の契約を確かめるため)
- `_seq_no`・`_primary_term` による版条件、`op_type=create` の競合(409。記録がないときの版条件つきの
  書き込み・削除も 409)
- PIT(開いた時点の見える状態のスナップショット)と `search_after`、PIT を閉じるまで開いたままの数
- `_bulk` の delete(存在しない ID は `status: 404`・`result: not_found`・`errors: false`)
- 例外・項目ごとの失敗の差し込み(`fail_on`、`fail_bulk_items`)、応答の一部の差し替え(部分失敗・
  `timed_out`。`patch_response`)、PIT の期限切れ(`expire_pits`)
- PIT の検索の保護: 2 ページ目以降に `search_after` がない・同じ PIT での検索が多すぎる、は
  `AssertionError`(`search_after` を外した実装が、無限に同じページを読んでハングしないように)
- 部分結果を許さないパラメータ(`allow_partial_search_results=false`・
  `allow_partial_pit_creation=false`)が付いていること(付いていなければ `AssertionError`)

再現しないもの(クエリの忠実度): 配列の項目(`term`・`terms` は値の完全一致で比べる)、空配列の
`exists`(実機では偽だが、ここでは値があるとみなす)、真偽値と整数の区別(`True == 1`)、
キーワード以外の型の並べ替え。Crawler の記録(スカラーの項目だけ)の範囲で十分とした。

条件なしの書き込み(`op_type` も版もない `index`・`delete`)は、Crawler の Repository にはない
操作なので、`AssertionError` にする。
"""

import copy
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import cmp_to_key
from typing import Any

from opensearchpy.exceptions import HTTP_EXCEPTIONS, TransportError
from opensearchpy.serializer import JSONSerializer

PRIMARY_TERM = 1
MAX_SEARCHES_PER_PIT = 1_000

GET = "get"
INDEX = "index"
DELETE = "delete"
REFRESH = "refresh"
SEARCH = "search"
CREATE_PIT = "create_pit"
DELETE_PIT = "delete_pit"
BULK = "bulk"


@dataclass(frozen=True)
class RecordedRequest:
    operation: str
    method: str
    url: str
    params: dict[str, str]
    body: Any


@dataclass
class _Doc:
    source: dict[str, Any]
    seq_no: int


@dataclass
class _Failure:
    error: Exception
    remaining: int | None
    skip: int


@dataclass
class _ResponsePatch:
    updates: dict[str, Any]
    remaining: int | None
    skip: int


@dataclass
class _ItemFailure:
    status: int
    error_type: str
    remaining: int | None


@dataclass
class _Index:
    docs: dict[str, _Doc] = field(default_factory=dict)
    visible: dict[str, _Doc] = field(default_factory=dict)  # 検索に見える状態(refresh で更新)


class FakeOpenSearchTransport:
    def __init__(self) -> None:
        # opensearch-py の `bulk` が、本文の組み立てに使う。
        self.serializer = JSONSerializer()
        self.requests: list[RecordedRequest] = []
        self._indexes: dict[str, _Index] = {}
        self._next_seq_no = 0
        self._next_pit_number = 0
        self._pits: dict[str, dict[str, _Doc]] = {}
        self._pit_search_counts: dict[str, int] = {}
        self._response_patches: dict[str, list[_ResponsePatch]] = {}
        self._failures: dict[str, list[_Failure]] = {}
        self._item_failures: dict[str, _ItemFailure] = {}

    # --- テストの準備・確認用 ---

    @property
    def open_pit_ids(self) -> list[str]:
        return sorted(self._pits)

    def operations(self) -> list[str]:
        return [request.operation for request in self.requests]

    def requests_of(self, operation: str) -> list[RecordedRequest]:
        return [request for request in self.requests if request.operation == operation]

    def fail_on(
        self, operation: str, error: Exception, *, times: int | None = 1, skip: int = 0
    ) -> None:
        """`operation` を、`skip` 回通した後の `times` 回(None なら以後ずっと)失敗させる。"""
        self._failures.setdefault(operation, []).append(_Failure(error, times, skip))

    def fail_bulk_items(
        self,
        record_ids: Sequence[str],
        *,
        status: int = 429,
        error_type: str = "es_rejected_execution_exception",
        times: int | None = 1,
    ) -> None:
        """`_bulk` の delete で、これらの ID の項目だけを失敗させる(部分失敗)。"""
        for record_id in record_ids:
            self._item_failures[record_id] = _ItemFailure(status, error_type, times)

    def patch_response(
        self, operation: str, updates: dict[str, Any], *, times: int | None = 1, skip: int = 0
    ) -> None:
        """`operation` の成功の応答の最上位の項目を、`skip` 回通した後の `times` 回、差し替える。

        部分失敗(`{"_shards": {"failed": 1, ...}}`)や `{"timed_out": True}` の再現に使う。
        """
        self._response_patches.setdefault(operation, []).append(
            _ResponsePatch(updates, times, skip)
        )

    def expire_pits(self) -> None:
        """開いている PIT をすべて期限切れにする(次の検索が、期限切れの応答になる)。"""
        self._pits.clear()

    def refresh(self, index_name: str) -> None:
        """検索に見える状態を、最新にする(実機の `_refresh`)。開いている PIT には影響しない。"""
        index = self._index(index_name)
        index.visible.clear()
        index.visible.update(index.docs)

    def seed(self, index_name: str, record_id: str, source: dict[str, Any]) -> None:
        """記録を直接置く(別の書き手の書き込み)。検索には、次の refresh まで見えない。"""
        self._index(index_name).docs[record_id] = self._new_doc(source)

    def source_of(self, index_name: str, record_id: str) -> dict[str, Any] | None:
        doc = self._index(index_name).docs.get(record_id)
        return copy.deepcopy(doc.source) if doc is not None else None

    # --- opensearch-py の transport の窓口 ---

    def perform_request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        normalized_params = {name: _as_text(value) for name, value in (params or {}).items()}
        operation, handler, groups = self._route(method, url)
        self.requests.append(RecordedRequest(operation, method, url, normalized_params, body))
        self._raise_injected_failure(operation)
        return self._apply_response_patch(operation, handler(groups, normalized_params, body))

    def close(self) -> None:
        pass

    def _apply_response_patch(self, operation: str, response: Any) -> Any:
        patches = self._response_patches.get(operation, [])
        for patch in patches:
            if patch.skip > 0:
                patch.skip -= 1
                return response
            if patch.remaining is not None:
                patch.remaining -= 1
                if patch.remaining <= 0:
                    patches.remove(patch)
            return {**response, **patch.updates}
        return response

    # --- ルーティング ---

    def _route(
        self, method: str, url: str
    ) -> tuple[str, Callable[[tuple[str, ...], dict[str, str], Any], Any], tuple[str, ...]]:
        routes: list[tuple[str, str, str, Callable[..., Any]]] = [
            ("GET", r"/([^/]+)/_doc/([^/]+)", GET, self._get),
            ("PUT", r"/([^/]+)/_doc/([^/]+)", INDEX, self._index_document),
            ("DELETE", r"/([^/]+)/_doc/([^/]+)", DELETE, self._delete_document),
            ("POST", r"/([^/]+)/_refresh", REFRESH, self._refresh),
            ("POST", r"/([^/]+)/_search/point_in_time", CREATE_PIT, self._create_pit),
            ("DELETE", r"/_search/point_in_time", DELETE_PIT, self._delete_pit),
            ("POST", r"/([^/]+)/_search", SEARCH, self._search),
            ("POST", r"/_search", SEARCH, self._search),
            ("POST", r"/_bulk", BULK, self._bulk),
        ]
        for route_method, pattern, operation, handler in routes:
            match = re.fullmatch(pattern, url)
            if route_method == method and match is not None:
                return operation, handler, match.groups()
        raise AssertionError(f"the fake does not support: {method} {url}")

    def _raise_injected_failure(self, operation: str) -> None:
        failures = self._failures.get(operation, [])
        for failure in failures:
            if failure.skip > 0:
                failure.skip -= 1
                return
            if failure.remaining is not None:
                failure.remaining -= 1
                if failure.remaining <= 0:
                    failures.remove(failure)
            raise copy.copy(failure.error)

    # --- 記録の読み書き ---

    def _get(self, groups: tuple[str, ...], params: dict[str, str], body: Any) -> dict[str, Any]:
        index_name, record_id = groups
        doc = self._index(index_name).docs.get(record_id)
        if doc is None:
            raise _http_error(404, {"_index": index_name, "_id": record_id, "found": False})
        return {
            "_index": index_name,
            "_id": record_id,
            "found": True,
            "_source": copy.deepcopy(doc.source),
            "_seq_no": doc.seq_no,
            "_primary_term": PRIMARY_TERM,
        }

    def _index_document(
        self, groups: tuple[str, ...], params: dict[str, str], body: Any
    ) -> dict[str, Any]:
        index_name, record_id = groups
        index = self._index(index_name)
        existing = index.docs.get(record_id)
        if params.get("op_type") == "create":
            if existing is not None:
                raise _version_conflict()
        elif "if_seq_no" in params:
            self._check_version(existing, params)
        else:
            raise AssertionError("unconditional index is not an operation of the Repository")
        index.docs[record_id] = self._new_doc(body)
        return {
            "_index": index_name,
            "_id": record_id,
            "result": "created" if existing is None else "updated",
            "_seq_no": index.docs[record_id].seq_no,
            "_primary_term": PRIMARY_TERM,
        }

    def _delete_document(
        self, groups: tuple[str, ...], params: dict[str, str], body: Any
    ) -> dict[str, Any]:
        index_name, record_id = groups
        index = self._index(index_name)
        if "if_seq_no" not in params:
            raise AssertionError("unconditional delete is not an operation of the Repository")
        self._check_version(index.docs.get(record_id), params)
        del index.docs[record_id]
        self._next_seq_no += 1
        return {"_index": index_name, "_id": record_id, "result": "deleted"}

    def _refresh(
        self, groups: tuple[str, ...], params: dict[str, str], body: Any
    ) -> dict[str, Any]:
        self.refresh(groups[0])
        return {"_shards": {"total": 1, "successful": 1, "failed": 0}}

    # --- 検索・PIT ---

    def _create_pit(
        self, groups: tuple[str, ...], params: dict[str, str], body: Any
    ) -> dict[str, Any]:
        assert "keep_alive" in params
        assert params.get("allow_partial_pit_creation") == "false"
        self._next_pit_number += 1
        pit_id = f"pit-{self._next_pit_number}"
        # 開いた時点の見える状態のコピー(以後の書き込み・refresh の影響を受けない)。
        self._pits[pit_id] = dict(self._index(groups[0]).visible)
        return {
            "pit_id": pit_id,
            "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
            "creation_time": 0,
        }

    def _delete_pit(
        self, groups: tuple[str, ...], params: dict[str, str], body: Any
    ) -> dict[str, Any]:
        results = []
        for pit_id in body["pit_id"]:
            results.append(
                {"pit_id": pit_id, "successful": self._pits.pop(pit_id, None) is not None}
            )
        return {"pits": results}

    def _search(self, groups: tuple[str, ...], params: dict[str, str], body: Any) -> dict[str, Any]:
        assert params.get("allow_partial_search_results") == "false"
        pit = body.get("pit")
        if pit is not None:
            assert "keep_alive" in pit
            if pit["id"] not in self._pits:
                raise _http_error(404, _missing_search_context_body())
            self._guard_pit_search(pit["id"], body)
            visible = self._pits[pit["id"]]
        else:
            visible = self._index(groups[0]).visible
        assert body.get("seq_no_primary_term") is True
        orders = [_sort_order(entry) for entry in body["sort"]]
        matching = [
            (record_id, doc)
            for record_id, doc in visible.items()
            if _matches(body["query"], doc.source)
        ]
        matching.sort(
            key=cmp_to_key(
                lambda a, b: _compare(
                    _sort_values(a[1], orders), _sort_values(b[1], orders), orders
                )
            )
        )
        search_after = body.get("search_after")
        if search_after is not None:
            matching = [
                item
                for item in matching
                if _compare(_sort_values(item[1], orders), search_after, orders) > 0
            ]
        hits = [
            {
                "_id": record_id,
                "_source": copy.deepcopy(doc.source),
                "_seq_no": doc.seq_no,
                "_primary_term": PRIMARY_TERM,
                "sort": _sort_values(doc, orders),
            }
            for record_id, doc in matching[: body["size"]]
        ]
        response: dict[str, Any] = {
            "took": 1,
            "timed_out": False,
            "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
            "hits": {"hits": hits},
        }
        if pit is not None:
            response["pit_id"] = pit["id"]
        return response

    def _guard_pit_search(self, pit_id: str, body: dict[str, Any]) -> None:
        """`search_after` を渡さずに同じ PIT を読み続ける実装(無限ループ)を、失敗として検出する。"""
        count = self._pit_search_counts.get(pit_id, 0)
        assert count == 0 or "search_after" in body, "search_after is missing after the first page"
        assert count < MAX_SEARCHES_PER_PIT, "too many searches on one PIT"
        self._pit_search_counts[pit_id] = count + 1

    # --- バルク削除 ---

    def _bulk(self, groups: tuple[str, ...], params: dict[str, str], body: Any) -> dict[str, Any]:
        lines = [json.loads(line) for line in body.splitlines() if line.strip()]
        items = []
        has_errors = False
        for line in lines:
            assert list(line) == ["delete"], "the Repository only bulk-deletes"
            index_name, record_id = line["delete"]["_index"], line["delete"]["_id"]
            item = self._bulk_delete_item(index_name, record_id)
            has_errors = has_errors or "error" in item
            items.append({"delete": item})
        return {"errors": has_errors, "items": items}

    def _bulk_delete_item(self, index_name: str, record_id: str) -> dict[str, Any]:
        item: dict[str, Any] = {"_index": index_name, "_id": record_id}
        failure = self._take_item_failure(record_id)
        if failure is not None:
            return {**item, "status": failure.status, "error": {"type": failure.error_type}}
        index = self._index(index_name)
        if record_id not in index.docs:
            return {**item, "status": 404, "result": "not_found"}
        del index.docs[record_id]
        self._next_seq_no += 1
        return {**item, "status": 200, "result": "deleted"}

    def _take_item_failure(self, record_id: str) -> _ItemFailure | None:
        failure = self._item_failures.get(record_id)
        if failure is None:
            return None
        if failure.remaining is not None:
            failure.remaining -= 1
            if failure.remaining <= 0:
                del self._item_failures[record_id]
        return failure

    # --- 内部 ---

    def _index(self, index_name: str) -> _Index:
        return self._indexes.setdefault(index_name, _Index())

    def _new_doc(self, source: dict[str, Any]) -> _Doc:
        doc = _Doc(source=copy.deepcopy(source), seq_no=self._next_seq_no)
        self._next_seq_no += 1
        return doc

    @staticmethod
    def _check_version(existing: _Doc | None, params: dict[str, str]) -> None:
        # 記録がない場合も 409(実機の `version_conflict_engine_exception`)。
        if (
            existing is None
            or existing.seq_no != int(params["if_seq_no"])
            or int(params["if_primary_term"]) != PRIMARY_TERM
        ):
            raise _version_conflict()


def _as_text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _http_error(status: int, info: dict[str, Any]) -> TransportError:
    error_class = HTTP_EXCEPTIONS.get(status, TransportError)
    return error_class(status, "error", info)


def _missing_search_context_body() -> dict[str, Any]:
    """期限切れ・閉じられた PIT の応答。実機(3.9.0)は、404 の `search_phase_execution_exception`
    の `root_cause` に `search_context_missing_exception` を入れて返す。"""
    return {
        "error": {
            "root_cause": [{"type": "search_context_missing_exception", "reason": "No context"}],
            "type": "search_phase_execution_exception",
            "reason": "all shards failed",
        },
        "status": 404,
    }


def _version_conflict() -> TransportError:
    return _http_error(409, {"error": {"type": "version_conflict_engine_exception"}, "status": 409})


def _matches(query: dict[str, Any], source: dict[str, Any]) -> bool:
    if "match_all" in query:
        return True
    clauses = query["bool"]
    return all(_clause_matches(clause, source) for clause in clauses["filter"]) and not any(
        _clause_matches(clause, source) for clause in clauses["must_not"]
    )


def _clause_matches(clause: dict[str, Any], source: dict[str, Any]) -> bool:
    if "term" in clause:
        ((name, value),) = clause["term"].items()
        return source.get(name) == value
    if "terms" in clause:
        ((name, values),) = clause["terms"].items()
        return source.get(name) in values
    if "exists" in clause:
        return source.get(clause["exists"]["field"]) is not None
    raise AssertionError(f"the fake does not support the clause: {clause}")


def _sort_order(entry: dict[str, str]) -> tuple[str, bool]:
    ((name, order),) = entry.items()
    return name, order == "desc"


def _sort_values(doc: _Doc, orders: list[tuple[str, bool]]) -> list[Any]:
    return [doc.source.get(name) for name, _ in orders]


def _compare(left: list[Any], right: list[Any], orders: list[tuple[str, bool]]) -> int:
    """並べ替えの順での比較。値のない記録(None)は、昇順でも降順でも末尾。"""
    for (_, descending), left_value, right_value in zip(orders, left, right, strict=True):
        if left_value == right_value:
            continue
        if left_value is None:
            return 1
        if right_value is None:
            return -1
        result = -1 if left_value < right_value else 1
        return -result if descending else result
    return 0
