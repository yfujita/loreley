"""読み取り専用の保証(D 6章 R8。C 2.3・11章 8)の AST 検査。

OpenSearch 側(R8 (a)〜(c))。Crawler クライアント(d)とプローブ(e)は、その実装時に足す。

- (a) 生の OpenSearch クライアントを呼ぶ場所は `readonly_client.py` だけで、呼んでよい属性チェーンは
  **名前空間つきで** `search`・`msearch`・`mget`・`cluster.health`・`cat.indices`・`cat.shards`・
  `cat.nodes` の 7 つ(最後の属性名だけで判定しない。`indices.get` が `get` で通らないように)。
- (b) ラッパーの公開メソッドの集合が固定(7 つ)で、引数は明示のものだけ(`**kwargs`・`**params` の
  素通しを書かない)。
- (c) Reader の Protocol と実装に、書き込みを表すメソッド名がない。

検査の対象は、名前に `client` を含む属性チェーンの呼び出し(`client`・`self._raw_client.cat` など。
Indexer の `test_write_rules.py` と同じ流儀)。限界: 動的な呼び出し(`getattr(client, name)(...)`)、
`client` を含まない名前へ代入し直したクライアント、`transport.perform_request(...)` のような
低水準の呼び出しは検出できない。Reader は、ラッパーを `client` を含まない名前(`readonly`)で持つ。
"""

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

OPENSEARCH_DIRECTORY = "infrastructure/opensearch"
PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "loreley_api"

READONLY_CLIENT_FILE = f"{OPENSEARCH_DIRECTORY}/readonly_client.py"
WRAPPER_CLASS = "ReadOnlyOpenSearch"
CLIENT_NAME_MARKER = "client"

# 公開メソッド → 生のクライアントの呼び先(名前空間つき)。
ALLOWED_CALLS_BY_METHOD: dict[str, str] = {
    "search": "search",
    "msearch": "msearch",
    "mget": "mget",
    "cluster_health": "cluster.health",
    "cat_indices": "cat.indices",
    "cat_shards": "cat.shards",
    "cat_nodes": "cat.nodes",
}
ALLOWED_CALLS = frozenset(ALLOWED_CALLS_BY_METHOD.values())

# 書き込み・索引管理・`refresh`・`scroll`・PIT・スクリプトを表す、メソッド名の最初の語。
WRITE_VERBS = frozenset(
    {
        "index",
        "create",
        "update",
        "delete",
        "remove",
        "bulk",
        "put",
        "post",
        "save",
        "write",
        "insert",
        "upsert",
        "add",
        "set",
        "reindex",
        "refresh",
        "flush",
        "forcemerge",
        "scroll",
        "clear",
        "pit",
        "script",
        "execute",
        "apply",
        "register",
        "start",
        "cancel",
        "truncate",
        "drop",
        "open",
        "close",
        "clone",
        "shrink",
        "split",
        "rollover",
    }
)

# Reader の実装ファイル → (実装クラス, Protocol)。
READER_FILES: dict[str, tuple[str, str]] = {
    "sources_reader.py": ("OpenSearchSourcesReader", "SourcesReader"),
    "jobs_reader.py": ("OpenSearchJobsReader", "JobsReader"),
    "deletions_reader.py": ("OpenSearchDeletionsReader", "DeletionsReader"),
    "search_index_reader.py": ("OpenSearchSearchIndexReader", "SearchIndexReader"),
    "counts_reader.py": ("OpenSearchCountsReader", "CountsReader"),
    "cluster_reader.py": ("OpenSearchClusterReader", "ClusterReader"),
}
PORTS_FILE = f"{OPENSEARCH_DIRECTORY}/ports.py"


@dataclass(frozen=True)
class ClientCall:
    name: str  # 名前空間つきの呼び先(`cat.indices` など)
    line: int
    forwards_arbitrary_arguments: bool  # `**kwargs`・`*args` の素通し


def load_sources(directory: str = OPENSEARCH_DIRECTORY) -> dict[str, str]:
    """`directory` 配下のソース(パッケージルートからの相対パス → ソース)。"""
    return {
        path.relative_to(PACKAGE_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in (PACKAGE_ROOT / directory).rglob("*.py")
    }


def attribute_chain(node: ast.expr) -> list[str] | None:
    """`self._raw_client.cat.indices` → `["self", "_raw_client", "cat", "indices"]`。"""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return parts[::-1]


def find_client_calls(tree: ast.AST) -> list[ClientCall]:
    """名前に `client` を含む要素から始まる属性チェーンの呼び出し。

    `client` を含む最初の要素より後ろを、名前空間つきの呼び先とする
    (`self._raw_client.cluster.health(...)` → `cluster.health`)。
    """
    calls: list[ClientCall] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        chain = attribute_chain(node.func)
        if chain is None:
            continue
        # 最後の要素は呼ばれるメソッド名なので、受け手(それより前)から `client` を探す。
        marker_positions = [
            position
            for position, part in enumerate(chain[:-1])
            if CLIENT_NAME_MARKER in part.lower()
        ]
        if not marker_positions:
            continue
        calls.append(
            ClientCall(
                name=".".join(chain[marker_positions[0] + 1 :]),
                line=node.lineno,
                forwards_arbitrary_arguments=_forwards_arbitrary_arguments(node),
            )
        )
    return calls


def _forwards_arbitrary_arguments(call: ast.Call) -> bool:
    has_starred_argument = any(isinstance(argument, ast.Starred) for argument in call.args)
    has_double_star_keyword = any(keyword.arg is None for keyword in call.keywords)
    return has_starred_argument or has_double_star_keyword


def find_disallowed_client_calls(sources: Mapping[str, str]) -> list[str]:
    """(a): 許可リストにない呼び先、または `readonly_client.py` 以外での呼び出し。"""
    problems: list[str] = []
    for path, source in sorted(sources.items()):
        for call in find_client_calls(ast.parse(source)):
            where = f"{path}:{call.line}"
            if path != READONLY_CLIENT_FILE:
                problems.append(
                    f"{where} calls the raw client ({call.name}) outside {WRAPPER_CLASS}"
                )
            elif call.name not in ALLOWED_CALLS:
                problems.append(f"{where} calls {call.name}, which is not on the allow list")
    return problems


def find_argument_forwarding(sources: Mapping[str, str]) -> list[str]:
    """(b): 生のクライアントの呼び出しへ、`**kwargs`・`*args` を素通ししている箇所。"""
    return [
        f"{path}:{call.line} forwards arbitrary arguments to {call.name}"
        for path, source in sorted(sources.items())
        for call in find_client_calls(ast.parse(source))
        if call.forwards_arbitrary_arguments
    ]


def find_class(tree: ast.AST, name: str) -> ast.ClassDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def methods_of(class_node: ast.ClassDef) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node for node in class_node.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]


def public_method_names(class_node: ast.ClassDef) -> set[str]:
    return {method.name for method in methods_of(class_node) if not method.name.startswith("_")}


def find_variadic_parameters(tree: ast.AST) -> list[str]:
    """(b): `*args`・`**kwargs` を受ける関数(ラッパーの中では、任意の引数を受けてはならない)。"""
    return [
        f"{node.name}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and (node.args.vararg is not None or node.args.kwarg is not None)
    ]


def find_write_named_methods(class_node: ast.ClassDef) -> list[str]:
    """(c): 書き込みを表す名前の公開メソッド。最初の語(`delete_job` → `delete`)で判定する。"""
    return [
        method.name
        for method in methods_of(class_node)
        if not method.name.startswith("_") and method.name.split("_")[0] in WRITE_VERBS
    ]


def calls_by_method(class_node: ast.ClassDef) -> dict[str, set[str]]:
    """ラッパーの公開メソッドごとの、生のクライアントの呼び先。"""
    return {
        method.name: {call.name for call in find_client_calls(method)}
        for method in methods_of(class_node)
        if not method.name.startswith("_")
    }


def wrapper_class(sources: Mapping[str, str]) -> ast.ClassDef:
    class_node = find_class(ast.parse(sources[READONLY_CLIENT_FILE]), WRAPPER_CLASS)
    assert class_node is not None
    return class_node


# --- 実際のソース ---


def test_the_opensearch_sources_are_found() -> None:
    sources = load_sources()

    assert READONLY_CLIENT_FILE in sources
    assert PORTS_FILE in sources
    assert {f"{OPENSEARCH_DIRECTORY}/{name}" for name in READER_FILES} <= set(sources)


def test_the_raw_client_is_called_only_in_the_wrapper_and_only_with_allowed_apis() -> None:  # (a)
    sources = load_sources()

    assert find_disallowed_client_calls(sources) == []
    # 空振りしていないことの確認: 許可リストの 7 つがすべて、ラッパーで呼ばれている。
    called = {call.name for call in find_client_calls(ast.parse(sources[READONLY_CLIENT_FILE]))}
    assert called == ALLOWED_CALLS


def test_opensearchpy_is_imported_only_under_the_opensearch_infrastructure() -> None:
    """生のクライアントの型・生成は `infrastructure/opensearch` の外へ出さない(R5 の補強)。"""
    importers = [
        path
        for path, source in load_sources("").items()
        if any(
            isinstance(node, ast.Import | ast.ImportFrom) and "opensearchpy" in ast.unparse(node)
            for node in ast.walk(ast.parse(source))
        )
    ]

    assert importers  # 空振りしていない
    assert all(path.startswith(f"{OPENSEARCH_DIRECTORY}/") for path in importers)


def test_each_wrapper_method_calls_exactly_its_own_api() -> None:  # (a)(b)
    wrapper = wrapper_class(load_sources())

    assert calls_by_method(wrapper) == {
        method: {call} for method, call in ALLOWED_CALLS_BY_METHOD.items()
    }


def test_the_wrapper_public_methods_are_the_seven_allowed_ones() -> None:  # (b)
    assert public_method_names(wrapper_class(load_sources())) == set(ALLOWED_CALLS_BY_METHOD)


def test_the_wrapper_does_not_forward_arbitrary_arguments() -> None:  # (b)
    sources = load_sources()

    assert find_argument_forwarding(sources) == []
    assert find_variadic_parameters(ast.parse(sources[READONLY_CLIENT_FILE])) == []


def test_the_wrapper_has_no_write_named_method() -> None:  # (b)
    assert find_write_named_methods(wrapper_class(load_sources())) == []


def test_reader_protocols_have_no_write_named_methods() -> None:  # (c)
    tree = ast.parse(load_sources()[PORTS_FILE])

    for _, protocol_name in READER_FILES.values():
        protocol = find_class(tree, protocol_name)
        assert protocol is not None, protocol_name
        assert public_method_names(protocol), protocol_name  # 空振りしていない
        assert find_write_named_methods(protocol) == [], protocol_name


def test_reader_implementations_have_exactly_the_protocol_methods() -> None:  # (c)
    sources = load_sources()
    ports = ast.parse(sources[PORTS_FILE])

    for file_name, (class_name, protocol_name) in READER_FILES.items():
        implementation = find_class(
            ast.parse(sources[f"{OPENSEARCH_DIRECTORY}/{file_name}"]), class_name
        )
        protocol = find_class(ports, protocol_name)
        assert implementation is not None, class_name
        assert protocol is not None, protocol_name
        assert public_method_names(implementation) == public_method_names(protocol), class_name
        assert find_write_named_methods(implementation) == [], class_name


def test_readers_hold_the_wrapper_not_a_raw_client() -> None:
    """Reader は、ラッパーを `client` を含む名前で持たない(生のクライアントと区別するため)。"""
    sources = load_sources()

    for file_name in READER_FILES:
        assert find_client_calls(ast.parse(sources[f"{OPENSEARCH_DIRECTORY}/{file_name}"])) == []


# --- 検出器の自己テスト(合成ソース。負例が空振りしない) ---

WRAPPER_PATH = READONLY_CLIENT_FILE
OTHER_PATH = f"{OPENSEARCH_DIRECTORY}/jobs_reader.py"


def disallowed(source: str, path: str = WRAPPER_PATH) -> list[str]:
    return find_disallowed_client_calls({path: source})


@pytest.mark.parametrize(
    "call",
    [
        "search(index=i, body=b)",
        "msearch(body=b)",
        "mget(index=i, body=b)",
        "cluster.health()",
        "cat.indices(format='json')",
        "cat.shards()",
        "cat.nodes()",
    ],
)
def test_an_allowed_call_in_the_wrapper_is_accepted(call: str) -> None:
    assert disallowed(f"self._raw_client.{call}") == []
    assert disallowed(f"client.{call}") == []


@pytest.mark.parametrize(
    "call",
    [
        "index(index='i', body={})",
        "create(index='i', id='1', body={})",
        "update(index='i', id='1', body={})",
        "delete(index='i', id='1')",
        "bulk(body=[])",
        "delete_by_query(index='i', body={})",
        "update_by_query(index='i', body={})",
        "reindex(body={})",
        "scroll(scroll_id='x')",
        "clear_scroll()",
        "create_pit(index='i')",
        "get(index='i', id='1')",
        "count(index='i')",
        "indices.refresh(index='i')",
        "indices.get(index='i')",  # 最後の名前 `get` だけで判定すると通ってしまう
        "indices.create(index='i')",
        "indices.delete(index='i')",
        "cluster.put_settings(body={})",
        "cluster.state()",
        "cat.health()",  # `cat.*` でも許可は 3 つだけ
        "transport.perform_request('POST', '/x')",
    ],
)
def test_a_call_outside_the_allow_list_is_detected(call: str) -> None:
    [problem] = disallowed(f"self._raw_client.{call}")

    assert "not on the allow list" in problem


def test_the_last_name_alone_does_not_make_a_namespaced_call_allowed() -> None:
    """`cat.health` は、`cluster.health` の最後の名前 `health` と同じでも許可されない。"""
    assert disallowed("client.cat.health()") != []
    assert disallowed("client.indices.search()") != []  # `search` と最後の名前は同じ
    assert disallowed("client.cluster.search()") != []


@pytest.mark.parametrize("receiver", ["client", "self._client", "os_client", "self.raw_client.cat"])
def test_any_client_named_receiver_is_covered(receiver: str) -> None:
    assert len(disallowed(f"{receiver}.index(index='i')")) == 1


def test_a_raw_client_call_outside_the_wrapper_is_detected_even_when_allowed() -> None:
    [problem] = disallowed("self._client.search(index='i', body={})", path=OTHER_PATH)

    assert "outside ReadOnlyOpenSearch" in problem


def test_calls_through_the_wrapper_are_not_raw_client_calls() -> None:
    source = "self._readonly.search(index='i', body={})\nself._readonly.cluster_health()"

    assert disallowed(source, path=OTHER_PATH) == []


def test_non_client_receivers_and_non_attribute_calls_are_ignored() -> None:
    source = "cache.index(1)\nitems.update({})\nsearch(index='i')\nOpenSearch(hosts=[])"

    assert disallowed(source) == []


@pytest.mark.parametrize(
    "call",
    [
        "client.search(**kwargs)",
        "client.search(index='i', **params)",
        "self._raw_client.cat.indices(*args)",
        "client.mget(index='i', body=b, **{'refresh': True})",
    ],
)
def test_forwarding_arbitrary_arguments_is_detected(call: str) -> None:
    [problem] = find_argument_forwarding({WRAPPER_PATH: call})

    assert "forwards arbitrary arguments" in problem


def test_explicit_arguments_are_not_reported_as_forwarding() -> None:
    assert find_argument_forwarding({WRAPPER_PATH: "client.search(index=i, body=b)"}) == []


@pytest.mark.parametrize(
    "signature", ["def search(self, **kwargs): ...", "def search(self, *args): ..."]
)
def test_a_variadic_wrapper_method_is_detected(signature: str) -> None:
    assert len(find_variadic_parameters(ast.parse(signature))) == 1


def test_a_wrapper_without_variadic_parameters_is_accepted() -> None:
    assert find_variadic_parameters(ast.parse("def search(self, *, index, body): ...")) == []


def class_of(source: str) -> ast.ClassDef:
    class_node = find_class(ast.parse(source), "Target")
    assert class_node is not None
    return class_node


def test_an_extra_public_wrapper_method_is_visible_to_the_surface_check() -> None:
    source = (
        "class Target:\n"
        "    def search(self): ...\n"
        "    def delete(self): ...\n"
        "    def _helper(self): ...\n"
    )

    assert public_method_names(class_of(source)) == {"search", "delete"}


@pytest.mark.parametrize(
    "method",
    [
        "index_document",
        "create_job",
        "update_source",
        "delete_job",
        "bulk_load",
        "save",
        "refresh_index",
        "scroll_all",
        "put_script",
        "reindex",
        "close",
    ],
)
def test_a_write_named_method_is_detected(method: str) -> None:
    source = f"class Target:\n    def {method}(self): ...\n    def get_job(self): ...\n"

    assert find_write_named_methods(class_of(source)) == [method]


def test_read_named_methods_and_private_helpers_are_not_write_named() -> None:
    source = (
        "class Target:\n"
        "    def list_all(self): ...\n"
        "    def get_locks(self): ...\n"
        "    def latest_by_source(self): ...\n"
        "    def existing_ids(self): ...\n"
        "    def count_for_source(self): ...\n"
        "    def read(self): ...\n"
        "    def _delete_helper(self): ...\n"
    )

    assert find_write_named_methods(class_of(source)) == []


def test_calls_by_method_attributes_each_call_to_its_method() -> None:
    source = (
        "class Target:\n"
        "    def cluster_health(self):\n"
        "        return self._raw_client.cluster.health()\n"
        "    def search(self):\n"
        "        self._raw_client.cat.indices()\n"
        "        return self._raw_client.search()\n"
    )

    assert calls_by_method(class_of(source)) == {
        "cluster_health": {"cluster.health"},
        "search": {"cat.indices", "search"},
    }
