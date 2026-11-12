"""R6(領域ごとのアクセス)・R7(検索インデックスへの書き込みは条件付き)の機械的な検査。

import では検査できないため、インターフェースの面(抽象メソッドの集合)と、
OpenSearch クライアントの書き込み呼び出しの場所・引数を AST で固定する。
受け口は、名前に `client` を含む属性チェーン(`client`、`self._client.indices` など)。
動的な呼び出し(`getattr(client, name)(...)` など)や、`client` を含まない名前へ代入し直した
クライアント、`client.transport.perform_request(...)` のような低水準の呼び出しは検出できない。
"""

import ast
import typing
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from loreley_indexer.infrastructure.opensearch import (
    JobsReader,
    RecordFilter,
    SearchIndexRepository,
    SortKey,
    StoreJobsReader,
    StoreReader,
    StoreRepository,
)
from loreley_indexer.infrastructure.opensearch.results import StoredDocument

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "loreley_indexer"

CLIENT_NAME_MARKER = "client"
WRITE_METHODS = {
    "index",
    "create",
    "delete",
    "update",
    "bulk",
    "update_by_query",
    "delete_by_query",
    "reindex",
    # `client.indices.*`(インデックス自体の変更。create/delete は上と共通の名前)
    "put_mapping",
    "put_settings",
    "put_alias",
    "delete_alias",
    "update_aliases",
    "put_index_template",
    "delete_index_template",
}

# 書き込み呼び出しを置いてよいファイル(パッケージルートからの相対パス)と、そこで使ってよいメソッド。
ALLOWED_WRITE_SITES = {
    "infrastructure/opensearch/client_calls.py": {"index", "delete"},
    "infrastructure/opensearch/search_index_adapter.py": {"update", "delete_by_query"},
}


@dataclass(frozen=True)
class WriteCall:
    method: str
    keywords: frozenset[str]
    keyword_constants: Mapping[str, object]


def is_client_receiver(node: ast.expr) -> bool:
    """`client`、`self._client`、`self._client.indices` のように、クライアント由来と読める式か。"""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return False
    parts.append(node.id)
    return any(CLIENT_NAME_MARKER in part.lower() for part in parts)


def find_write_calls(source: str) -> list[WriteCall]:
    calls: list[WriteCall] = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if not is_client_receiver(node.func.value):
            continue
        if node.func.attr not in WRITE_METHODS:
            continue
        calls.append(
            WriteCall(
                method=node.func.attr,
                keywords=frozenset(kw.arg for kw in node.keywords if kw.arg is not None),
                keyword_constants={
                    kw.arg: kw.value.value
                    for kw in node.keywords
                    if kw.arg is not None and isinstance(kw.value, ast.Constant)
                },
            )
        )
    return calls


def find_helper_call_keywords(source: str, function_name: str) -> list[frozenset[str]]:
    """`function_name(...)` の呼び出しごとの、キーワード引数名の集合。"""
    return [
        frozenset(kw.arg for kw in node.keywords if kw.arg is not None)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == function_name
    ]


def read_source(relative_path: str) -> str:
    return (PACKAGE_ROOT / relative_path).read_text(encoding="utf-8")


# --- R6: インターフェースの面 ---


def test_search_index_repository_surface_is_fixed() -> None:
    assert SearchIndexRepository.__abstractmethods__ == {
        "fetch",
        "fetch_for_deletion",
        "create",
        "replace_if_unchanged",
        "raise_last_seen_at",
        "delete_if_unchanged",
        "search_document_ids",
        "count",
        "count_existing_ids",
        "refresh",
        "delete_by_query",
    }


def test_store_reader_has_no_write_methods() -> None:
    assert StoreReader.__abstractmethods__ == {"fetch", "list_records"}
    assert not any(
        hasattr(StoreReader, name) for name in ("save", "replace_if_unchanged", "delete")
    )


def test_store_repository_adds_only_the_known_write_methods() -> None:
    assert StoreRepository.__abstractmethods__ == {
        "fetch",
        "list_records",
        "save",
        "replace_if_unchanged",
        "delete",
    }


def test_jobs_reader_is_read_only_and_built_from_a_store_reader() -> None:
    assert JobsReader.__abstractmethods__ == {"fetch_lock", "is_maintenance_enabled"}
    public_methods = {name for name in vars(StoreJobsReader) if not name.startswith("_")}
    assert public_methods == {"fetch_lock", "is_maintenance_enabled"}
    assert typing.get_type_hints(StoreJobsReader.__init__)["jobs_store"] is StoreReader


def test_jobs_reader_works_with_a_store_that_cannot_write() -> None:
    class ReadOnlyStore(StoreReader):
        def fetch(self, record_id: str) -> StoredDocument | None:
            return None

        def list_records(
            self, record_filter: RecordFilter, sort: Sequence[SortKey], *, limit: int
        ) -> list[StoredDocument]:
            return []

    assert StoreJobsReader(ReadOnlyStore()).is_maintenance_enabled() is False


# --- R7: 書き込み呼び出しの場所と条件 ---


def test_client_write_calls_exist_only_in_the_opensearch_adapters() -> None:
    sites: dict[str, set[str]] = {}
    for path in PACKAGE_ROOT.rglob("*.py"):
        methods = {call.method for call in find_write_calls(path.read_text(encoding="utf-8"))}
        if methods:
            sites[path.relative_to(PACKAGE_ROOT).as_posix()] = methods
    assert sites == ALLOWED_WRITE_SITES


def test_every_search_index_write_is_conditional() -> None:
    source = read_source("infrastructure/opensearch/search_index_adapter.py")

    index_conditions = find_helper_call_keywords(source, "index_document")
    assert len(index_conditions) == 2  # create、replace_if_unchanged
    for keywords in index_conditions:
        assert "op_type" in keywords or {"if_seq_no", "if_primary_term"} <= keywords

    delete_conditions = find_helper_call_keywords(source, "delete_document")
    assert len(delete_conditions) == 1
    assert {"if_seq_no", "if_primary_term"} <= delete_conditions[0]

    direct_calls = {call.method: call for call in find_write_calls(source)}
    assert "retry_on_conflict" in direct_calls["update"].keywords
    assert direct_calls["delete_by_query"].keyword_constants.get("conflicts") == "proceed"


# --- 検査器の自己テスト ---


def test_detector_finds_unconditional_writes_in_other_places() -> None:
    source = (
        "def f(client):\n    client.index(index='i', id='1', body={})\n    client.get(index='i')"
    )
    assert [call.method for call in find_write_calls(source)] == ["index"]
    assert [call.method for call in find_write_calls("self._client.bulk(body=[])")] == ["bulk"]
    assert find_write_calls("other.index(1)") == []


@pytest.mark.parametrize(
    ("call", "method"),
    [
        ("client.indices.create(index='i')", "create"),
        ("self._client.indices.put_mapping(index='i', body={})", "put_mapping"),
        ("opensearch_client.indices.put_settings(body={})", "put_settings"),
        ("self.client.indices.delete(index='i')", "delete"),
        ("os_client.reindex(body={})", "reindex"),
    ],
)
def test_detector_finds_index_management_writes_through_any_client_attribute(
    call: str, method: str
) -> None:
    assert [found.method for found in find_write_calls(call)] == [method]


@pytest.mark.parametrize(
    "call", ["client.get(index='i')", "client.indices.exists(index='i')", "cache.create()"]
)
def test_detector_ignores_reads_and_non_client_receivers(call: str) -> None:
    assert find_write_calls(call) == []
