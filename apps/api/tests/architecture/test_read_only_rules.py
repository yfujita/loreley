"""読み取り専用の保証(D 6章 R8。C 2.3・11章 8)の AST 検査。

OpenSearch 側(R8 (a)〜(c))、Crawler クライアント(d)、死活確認のプローブ(e)。

- (a) 生の OpenSearch クライアントを呼ぶ場所は `readonly_client.py` だけで、呼んでよい属性チェーンは
  **名前空間つきで** `search`・`msearch`・`mget`・`cluster.health`・`cat.indices`・`cat.shards`・
  `cat.nodes` の 7 つ(最後の属性名だけで判定しない。`indices.get` が `get` で通らないように)。
- (b) ラッパーの公開メソッドの集合が固定(7 つ)で、引数は明示のものだけ(`**kwargs`・`**params` の
  素通しを書かない)。
- (c) Reader の Protocol と実装に、書き込みを表すメソッド名がない。
- (d) Crawler クライアントの公開操作は 6 つだけ(`CrawlerClient` と `HttpCrawlerClient`)で、任意の
  メソッド・パスを受け取る引数や `**kwargs` を持たない。パスのリテラル(`/sources`・`/jobs`)は
  `routes.py` だけにあり、経路は 6 つだけ。HTTP の送信は `http_client.py` の 1 か所で、メソッドと
  パスは `routes.py` の組み立て結果だけを使い、再送とリダイレクトの追従をしない指定
  (`retries=False`・`redirect=False`)にする。

(a)〜(c) の検査の対象は、名前に `client` を含む属性チェーンの呼び出し(`client`・
`self._raw_client.cat` など。Indexer の `test_write_rules.py` と同じ流儀)。限界: 動的な呼び出し
(`getattr(client, name)(...)`)、`client` を含まない名前へ代入し直したクライアント、
`transport.perform_request(...)` のような低水準の呼び出しは検出できない。Reader は、ラッパーを
`client` を含まない名前(`readonly`)で持つ。
- (e) プローブの HTTP は `GET` だけ。送信の呼び出しは `infrastructure/probes/http_probe.py` の
  1 か所で、メソッドは `"GET"` のリテラル、URL は引数 `url`(呼び出し側が設定から得た値)、
  再送とリダイレクトの追従をしない指定にする。`infrastructure/probes` にはパスのリテラルがなく、
  `services.dashboard` の `/healthz` だけが、確認に使う唯一のパス(C 11章 8 (c) の `GET /healthz`)。
  `opensearch` のプローブは、ラッパー経由の `cluster.health` だけ((a)(b) が検査する)。
(d) の限界: 文字列を連結して作ったパス(`"/" + name`)や、パスを別の定数に分けた書き方は検出できない
(パスのリテラルは先頭が `/` の文字列だけを見る)。送信の呼び出しは、名前(`request`・`urlopen` など)で
判定する。
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

# 書き込み・索引管理・`refresh`・`scroll`・PIT・スクリプトを表す語。メソッド名を `_` で分けた
# どの語でも判定する(`job_delete`・`source_purge` のように、動詞が後ろにある名前も拾う)。
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
        "purge",
        "erase",
        "mark",
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
    """(c): 書き込みを表す名前の公開メソッド。名前のどの語(`job_delete` → `delete`)でも判定する。"""
    return [
        method.name
        for method in methods_of(class_node)
        if not method.name.startswith("_") and not WRITE_VERBS.isdisjoint(method.name.split("_"))
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


def test_every_reader_file_is_registered_for_the_checks() -> None:
    """Reader を足したのに `READER_FILES` に登録し忘れて、検査から外れることを防ぐ。"""
    reader_files = {path.name for path in (PACKAGE_ROOT / OPENSEARCH_DIRECTORY).glob("*_reader.py")}

    assert reader_files == set(READER_FILES)


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
        "purge_old_jobs",
        "erase_source",
        "mark_done",
        "job_delete",  # 動詞が最初の語でない名前
        "force_refresh",
        "source_purge",
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


# --- (d) Crawler クライアント ---

CRAWLER_CLIENT_DIRECTORY = "infrastructure/crawler_client"
CRAWLER_CLIENT_FILE = f"{CRAWLER_CLIENT_DIRECTORY}/client.py"
CRAWLER_HTTP_CLIENT_FILE = f"{CRAWLER_CLIENT_DIRECTORY}/http_client.py"
CRAWLER_ROUTES_FILE = f"{CRAWLER_CLIENT_DIRECTORY}/routes.py"

# Crawler の 6 API に 1 対 1 の操作(B 9.2。C 4.8)。
CRAWLER_OPERATIONS = frozenset(
    {
        "register_source",
        "update_source",
        "start_delete_job",
        "start_crawl",
        "cancel_job",
        "release_lock",
    }
)
# Crawler に送る経路(メソッド, パスのテンプレート)のすべて(C 4.8)。
CRAWLER_ROUTES = frozenset(
    {
        ("POST", "/sources"),
        ("PUT", "/sources/{source_id}"),
        ("POST", "/sources/{source_id}/delete-jobs"),
        ("POST", "/sources/{source_id}/crawl-jobs"),
        ("POST", "/jobs/{job_id}/cancel"),
        ("DELETE", "/sources/{source_id}/lock"),
    }
)
HTTP_CLIENT_CLASS = "HttpCrawlerClient"
PROTOCOL_CLASS = "CrawlerClient"
# 公開の操作は、任意のメソッド・パス・URL・ヘッダを受け取る引数を持たない。
FORBIDDEN_PARAMETER_NAMES = frozenset(
    {"method", "path", "url", "uri", "route", "endpoint", "headers", "target"}
)
# urllib3 の送信を行うメソッド名(`PoolManager`・モジュールの `urllib3.request`)。
SEND_METHOD_NAMES = frozenset({"request", "urlopen", "request_encode_body", "request_encode_url"})
EXCHANGE_METHOD = "_send_once"


def find_path_literals(source: str) -> list[str]:
    """先頭が `/` の文字列(`/` だけは除く)。f 文字列の固定部分も含む。"""
    return [
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("/")
        and len(node.value) > 1
    ]


def find_path_literals_outside_routes(sources: Mapping[str, str]) -> list[str]:
    return [
        f"{path} has the path literal {literal!r}"
        for path, source in sorted(sources.items())
        if path != CRAWLER_ROUTES_FILE
        for literal in find_path_literals(source)
    ]


def find_route_templates(source: str) -> set[tuple[str, str]]:
    """`_Template("POST", "/sources")` の呼び出しから、(メソッド, パス)を集める。"""
    routes: set[tuple[str, str]] = set()
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != "_Template":
            continue
        arguments = [argument.value for argument in node.args if isinstance(argument, ast.Constant)]
        assert len(arguments) == 2, ast.unparse(node)
        routes.add((arguments[0], arguments[1]))
    return routes


def find_send_calls(tree: ast.AST) -> list[ast.Call]:
    """属性呼び出しで、メソッド名が urllib3 の送信を行うもの。"""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in SEND_METHOD_NAMES
    ]


def function_names_of_send_calls(tree: ast.AST) -> list[str | None]:
    """送信の呼び出しごとの、それを含む関数名(関数の外なら `None`)。"""
    in_function = {
        id(call): function.name
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
        for call in find_send_calls(function)
    }
    return [in_function.get(id(call)) for call in find_send_calls(tree)]


def find_send_outside_the_exchange(sources: Mapping[str, str]) -> list[str]:
    """送信の呼び出しが、`http_client.py` の `_send_once` の 1 か所だけであること。"""
    problems: list[str] = []
    for path, source in sorted(sources.items()):
        tree = ast.parse(source)
        calls = find_send_calls(tree)
        if path != CRAWLER_HTTP_CLIENT_FILE:
            problems += [
                f"{path}:{call.lineno} sends a request outside http_client.py" for call in calls
            ]
            continue
        problems += [
            f"{path} sends a request outside {EXCHANGE_METHOD}"
            for function_name in function_names_of_send_calls(tree)
            if function_name != EXCHANGE_METHOD
        ]
        if len(calls) > 1:
            problems.append(f"{path} sends a request in more than one place")
    return problems


def find_send_not_from_route(source: str) -> list[str]:
    """送信のメソッドとパスが、`route.method`・`route.path`(`routes.py` の結果)であること。"""
    problems: list[str] = []
    for call in find_send_calls(ast.parse(source)):
        method_argument = ast.unparse(call.args[0]) if call.args else ""
        url_argument = ast.unparse(call.args[1]) if len(call.args) > 1 else ""
        if method_argument != "route.method":
            problems.append(f"line {call.lineno}: the HTTP method is {method_argument!r}")
        if "route.path" not in url_argument:
            problems.append(f"line {call.lineno}: the URL does not use route.path")
        if _forwards_arbitrary_arguments(call):
            problems.append(f"line {call.lineno}: forwards arbitrary arguments")
    return problems


def find_send_without_safe_options(source: str) -> list[str]:
    """送信が、再送もリダイレクトの追従もしない指定(`retries=False`・`redirect=False`)であること。"""
    problems: list[str] = []
    for call in find_send_calls(ast.parse(source)):
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        for option in ("retries", "redirect"):
            value = keywords.get(option)
            if not (isinstance(value, ast.Constant) and value.value is False):
                problems.append(f"line {call.lineno}: {option} is not False")
    return problems


def parameter_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    arguments = function.args
    names = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    return {argument.arg for argument in names} - {"self"}


def find_open_ended_operations(class_node: ast.ClassDef) -> list[str]:
    """公開メソッドのうち、任意のメソッド・パスを受けうるもの(禁止の引数名・`*args`・`**kwargs`)。"""
    problems: list[str] = []
    for method in methods_of(class_node):
        if method.name.startswith("_"):
            continue
        forbidden = parameter_names(method) & FORBIDDEN_PARAMETER_NAMES
        if forbidden:
            problems.append(f"{method.name} accepts {sorted(forbidden)}")
        if method.args.vararg is not None or method.args.kwarg is not None:
            problems.append(f"{method.name} accepts variadic arguments")
    return problems


def route_calls_by_method(class_node: ast.ClassDef) -> dict[str, set[str]]:
    """公開メソッドごとの、`routes.<関数>(...)` の呼び先。"""
    return {
        method.name: {
            node.func.attr
            for node in ast.walk(method)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "routes"
        }
        for method in methods_of(class_node)
        if not method.name.startswith("_")
    }


def crawler_class(sources: Mapping[str, str], file: str, name: str) -> ast.ClassDef:
    class_node = find_class(ast.parse(sources[file]), name)
    assert class_node is not None, name
    return class_node


# --- (d) 実際のソース ---


def test_the_crawler_client_sources_are_found() -> None:
    sources = load_sources(CRAWLER_CLIENT_DIRECTORY)

    assert {CRAWLER_CLIENT_FILE, CRAWLER_HTTP_CLIENT_FILE, CRAWLER_ROUTES_FILE} <= set(sources)


def test_the_crawler_client_protocol_has_exactly_the_six_operations() -> None:
    protocol = crawler_class(
        load_sources(CRAWLER_CLIENT_DIRECTORY), CRAWLER_CLIENT_FILE, PROTOCOL_CLASS
    )

    assert public_method_names(protocol) == CRAWLER_OPERATIONS


def test_the_http_crawler_client_has_the_six_operations_and_close_only() -> None:
    http_client = crawler_class(
        load_sources(CRAWLER_CLIENT_DIRECTORY), CRAWLER_HTTP_CLIENT_FILE, HTTP_CLIENT_CLASS
    )

    assert public_method_names(http_client) == CRAWLER_OPERATIONS | {"close"}


def test_no_operation_of_the_crawler_client_accepts_an_arbitrary_method_or_path() -> None:
    sources = load_sources(CRAWLER_CLIENT_DIRECTORY)

    for file, name in [
        (CRAWLER_CLIENT_FILE, PROTOCOL_CLASS),
        (CRAWLER_HTTP_CLIENT_FILE, HTTP_CLIENT_CLASS),
    ]:
        assert find_open_ended_operations(crawler_class(sources, file, name)) == [], name


def test_each_operation_builds_its_own_fixed_route_and_nothing_else() -> None:
    http_client = crawler_class(
        load_sources(CRAWLER_CLIENT_DIRECTORY), CRAWLER_HTTP_CLIENT_FILE, HTTP_CLIENT_CLASS
    )

    calls = route_calls_by_method(http_client)

    assert calls.pop("close") == set()
    # 操作 `x` は `routes.x(...)` だけを呼ぶ(別の操作の経路を使い回さない)。
    assert calls == {operation: {operation} for operation in CRAWLER_OPERATIONS}


def test_the_path_literals_are_only_in_routes_py_and_are_the_six_routes() -> None:
    sources = load_sources(CRAWLER_CLIENT_DIRECTORY)

    assert find_path_literals_outside_routes(sources) == []
    assert find_route_templates(sources[CRAWLER_ROUTES_FILE]) == CRAWLER_ROUTES
    # 空振りしていない: routes.py のパスのリテラルは、6 経路のテンプレートだけ。
    assert set(find_path_literals(sources[CRAWLER_ROUTES_FILE])) == {
        path for _, path in CRAWLER_ROUTES
    }


def test_the_http_request_is_sent_in_one_place_with_the_method_and_path_of_a_route() -> None:
    sources = load_sources(CRAWLER_CLIENT_DIRECTORY)

    assert find_send_outside_the_exchange(sources) == []
    assert (
        len(find_send_calls(ast.parse(sources[CRAWLER_HTTP_CLIENT_FILE]))) == 1
    )  # 空振りしていない
    assert find_send_not_from_route(sources[CRAWLER_HTTP_CLIENT_FILE]) == []
    assert find_send_without_safe_options(sources[CRAWLER_HTTP_CLIENT_FILE]) == []


# --- (d) 検出器の自己テスト(合成ソース。負例が空振りしない) ---

OTHER_CRAWLER_FILE = f"{CRAWLER_CLIENT_DIRECTORY}/parsing.py"


@pytest.mark.parametrize(
    "source",
    [
        'PATH = "/sources"',
        'PATH = "/jobs/x/cancel"',
        'url = f"{base}/sources/{source_id}/lock"',
        'send("/anything")',
        "return '/healthz'",
    ],
)
def test_a_path_literal_outside_routes_py_is_detected(source: str) -> None:
    problems = find_path_literals_outside_routes({OTHER_CRAWLER_FILE: source})

    # f 文字列は、固定部分ごとに 1 件になる。
    assert problems
    assert all("path literal" in problem for problem in problems)


def test_a_path_literal_in_routes_py_is_accepted() -> None:
    assert find_path_literals_outside_routes({CRAWLER_ROUTES_FILE: 'PATH = "/sources"'}) == []


def test_a_slash_alone_and_non_path_text_are_not_path_literals() -> None:
    source = 'base_url.rstrip("/")\nx = "sources"\ny = "a/b"\nz = "Crawler /sources"'

    assert find_path_literals_outside_routes({OTHER_CRAWLER_FILE: source}) == []


def test_a_seventh_route_is_visible_to_the_route_check() -> None:
    source = '_A = _Template("POST", "/sources")\n_B = _Template("PATCH", "/admin/reset")'

    assert find_route_templates(source) == {("POST", "/sources"), ("PATCH", "/admin/reset")}
    assert find_route_templates(source) != CRAWLER_ROUTES


@pytest.mark.parametrize(
    "call",
    [
        "self._pool.request('GET', url)",
        "self._pool.urlopen('GET', url)",
        "urllib3.request('GET', url)",
        "http.request_encode_body('POST', url)",
    ],
)
def test_a_send_outside_http_client_is_detected(call: str) -> None:
    [problem] = find_send_outside_the_exchange({OTHER_CRAWLER_FILE: call})

    assert "outside http_client.py" in problem


def test_a_send_outside_the_exchange_function_is_detected() -> None:
    source = (
        "class HttpCrawlerClient:\n"
        "    def _send_once(self, route):\n"
        "        return self._pool.request(route.method, route.path)\n"
        "    def raw(self, route):\n"
        "        return self._pool.request(route.method, route.path)\n"
    )

    problems = find_send_outside_the_exchange({CRAWLER_HTTP_CLIENT_FILE: source})

    assert any("outside _send_once" in problem for problem in problems)
    assert any("more than one place" in problem for problem in problems)


def test_the_send_of_a_single_exchange_function_is_accepted() -> None:
    source = (
        "class HttpCrawlerClient:\n"
        "    def _send_once(self, route):\n"
        "        return self._pool.request(route.method, f'{self._base_url}{route.path}')\n"
    )

    assert find_send_outside_the_exchange({CRAWLER_HTTP_CLIENT_FILE: source}) == []
    assert find_send_not_from_route(source) == []


@pytest.mark.parametrize(
    "call",
    [
        "self._pool.request('POST', route.path)",  # メソッドが固定のリテラル
        "self._pool.request(method, route.path)",
        "self._pool.request(route.method, path)",
        "self._pool.request(route.method, '/sources')",
        "self._pool.request(route.method, route.path, **options)",
        "self._pool.request(*arguments)",
    ],
)
def test_a_send_that_does_not_use_the_method_and_path_of_a_route_is_detected(call: str) -> None:
    assert find_send_not_from_route(call) != []


@pytest.mark.parametrize(
    "signature",
    [
        "def call(self, method, path): ...",
        "def fetch(self, source_id, *, url): ...",
        "def start_crawl(self, source_id, route): ...",
        "def release_lock(self, source_id, **kwargs): ...",
        "def cancel_job(self, *args): ...",
        "def cancel_job(self, job_id, *, headers=None): ...",
    ],
)
def test_an_open_ended_operation_is_detected(signature: str) -> None:
    class_node = ast.parse(f"class Target:\n    {signature}\n").body[0]
    assert isinstance(class_node, ast.ClassDef)

    assert find_open_ended_operations(class_node) != []


def test_explicit_operations_and_private_helpers_are_not_open_ended() -> None:
    source = (
        "class Target:\n"
        "    def start_crawl(self, source_id, *, force_delete, rewrite_mode): ...\n"
        "    def _exchange(self, route, payload): ...\n"
    )
    class_node = ast.parse(source).body[0]
    assert isinstance(class_node, ast.ClassDef)

    assert find_open_ended_operations(class_node) == []


def test_an_extra_public_operation_is_visible_to_the_surface_check() -> None:
    source = "class Target:\n    def start_crawl(self): ...\n    def get(self, path): ...\n"

    assert public_method_names(class_of(source)) != CRAWLER_OPERATIONS


def test_route_calls_by_method_attributes_each_route_to_its_operation() -> None:
    source = (
        "class Target:\n"
        "    def cancel_job(self, job_id):\n"
        "        return self._exchange(routes.cancel_job(job_id))\n"
        "    def release_lock(self, source_id):\n"
        "        return self._exchange(routes.cancel_job(source_id))\n"
        "    def close(self): ...\n"
    )

    assert route_calls_by_method(class_of(source)) == {
        "cancel_job": {"cancel_job"},
        "release_lock": {"cancel_job"},  # 別の操作の経路を使う誤りが見える
        "close": set(),
    }


@pytest.mark.parametrize(
    "call",
    [
        "self._pool.request(route.method, route.path, retries=True, redirect=False)",
        "self._pool.request(route.method, route.path, retries=False, redirect=True)",
        "self._pool.request(route.method, route.path, retries=False)",
        "self._pool.request(route.method, route.path, redirect=False)",
        "self._pool.request(route.method, route.path, retries=0, redirect=False)",
        "self._pool.request(route.method, route.path, retries=retries, redirect=False)",
    ],
)
def test_a_send_that_may_retry_or_follow_a_redirect_is_detected(call: str) -> None:
    assert len(find_send_without_safe_options(call)) == 1


def test_a_send_with_retries_and_redirect_disabled_is_accepted() -> None:
    call = "self._pool.request(route.method, route.path, retries=False, redirect=False)"

    assert find_send_without_safe_options(call) == []


# --- (e) 死活確認のプローブ(HTTP は GET だけ) ---

PROBES_DIRECTORY = "infrastructure/probes"
PROBES_HTTP_FILE = f"{PROBES_DIRECTORY}/http_probe.py"
PROBES_PORTS_FILE = f"{PROBES_DIRECTORY}/ports.py"
HEALTH_PROBE_FILE = f"{OPENSEARCH_DIRECTORY}/health_probe.py"
DASHBOARD_SERVICE_FILE = "admin/services/dashboard.py"
HTTP_PROBE_CLASS = "HttpHealthProbe"
HTTP_PROBE_PROTOCOL = "HttpHealthCheck"
PROBE_SEND_METHOD = "GET"
# 確認先の URL を受け取る引数の名前(`self._pool.request("GET", url, ...)`)。
PROBE_URL_ARGUMENT = "url"
# `crawler`・`indexer` の確認に使う、唯一のパス。
HEALTH_PATH = "/healthz"


def find_probe_sends_outside_http_probe(sources: Mapping[str, str]) -> list[str]:
    """送信の呼び出しが、`http_probe.py` の中の 1 か所だけであること。"""
    problems: list[str] = []
    for path, source in sorted(sources.items()):
        calls = find_send_calls(ast.parse(source))
        if path != PROBES_HTTP_FILE:
            problems += [
                f"{path}:{call.lineno} sends a request outside http_probe.py" for call in calls
            ]
        elif len(calls) > 1:
            problems.append(f"{path} sends a request in more than one place")
    return problems


def find_probe_sends_not_get_of_the_given_url(source: str) -> list[str]:
    """送信のメソッドが `"GET"` のリテラルで、URL が引数 `url` そのものであること。"""
    problems: list[str] = []
    for call in find_send_calls(ast.parse(source)):
        method_argument = call.args[0] if call.args else None
        url_argument = ast.unparse(call.args[1]) if len(call.args) > 1 else ""
        is_get = (
            isinstance(method_argument, ast.Constant) and method_argument.value == PROBE_SEND_METHOD
        )
        if not is_get:
            shown = ast.unparse(method_argument) if method_argument is not None else ""
            problems.append(f"line {call.lineno}: the HTTP method is {shown!r}, not GET")
        if url_argument != PROBE_URL_ARGUMENT:
            problems.append(
                f"line {call.lineno}: the URL is {url_argument!r}, not the url argument"
            )
        if _forwards_arbitrary_arguments(call):
            problems.append(f"line {call.lineno}: forwards arbitrary arguments")
    return problems


def find_probe_sends_that_read_the_body(source: str) -> list[str]:
    """本文を先読みしない指定(`preload_content=False`)であること(読むと応答の大きさに左右される)。"""
    problems: list[str] = []
    for call in find_send_calls(ast.parse(source)):
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        value = keywords.get("preload_content")
        if not (isinstance(value, ast.Constant) and value.value is False):
            problems.append(f"line {call.lineno}: preload_content is not False")
    return problems


def accepts_only_the_url(operation: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """確認先の URL だけを受ける(メソッド・ヘッダ・`*args`・`**kwargs` を受け取れない)。"""
    return (
        parameter_names(operation) == {PROBE_URL_ARGUMENT}
        and operation.args.vararg is None
        and operation.args.kwarg is None
    )


def find_path_literals_in_probes(sources: Mapping[str, str]) -> list[str]:
    return [
        f"{path} has the path literal {literal!r}"
        for path, source in sorted(sources.items())
        for literal in find_path_literals(source)
    ]


# --- (e) 実際のソース ---


def test_the_probe_sources_are_found() -> None:
    sources = load_sources(PROBES_DIRECTORY)

    assert {PROBES_HTTP_FILE, PROBES_PORTS_FILE} <= set(sources)
    assert HEALTH_PROBE_FILE in load_sources(OPENSEARCH_DIRECTORY)


def test_the_http_probe_sends_a_get_for_the_given_url_only_in_one_place() -> None:
    sources = load_sources(PROBES_DIRECTORY)

    assert find_probe_sends_outside_http_probe(sources) == []
    assert len(find_send_calls(ast.parse(sources[PROBES_HTTP_FILE]))) == 1  # 空振りしていない
    assert find_probe_sends_not_get_of_the_given_url(sources[PROBES_HTTP_FILE]) == []
    # 再送もリダイレクトの追従もしない。本文は先読みしない。
    assert find_send_without_safe_options(sources[PROBES_HTTP_FILE]) == []
    assert find_probe_sends_that_read_the_body(sources[PROBES_HTTP_FILE]) == []


def test_the_http_probe_has_no_other_way_to_choose_the_method_or_the_target() -> None:
    sources = load_sources(PROBES_DIRECTORY)
    protocol = crawler_class(sources, PROBES_PORTS_FILE, HTTP_PROBE_PROTOCOL)
    http_probe = crawler_class(sources, PROBES_HTTP_FILE, HTTP_PROBE_CLASS)

    assert public_method_names(protocol) == {"check"}
    assert public_method_names(http_probe) == {"check", "close"}
    for class_node in (protocol, http_probe):
        check = next(method for method in methods_of(class_node) if method.name == "check")
        assert accepts_only_the_url(check), class_node.name
    assert find_variadic_parameters(ast.parse(sources[PROBES_HTTP_FILE])) == []


def test_the_probes_have_no_path_literal_and_only_the_dashboard_adds_healthz() -> None:
    probe_sources = load_sources(PROBES_DIRECTORY)
    service_source = load_sources("admin/services")["admin/services/dashboard.py"]

    assert find_path_literals_in_probes(probe_sources) == []
    # 空振りしていない: 確認に使うパスは、`services.dashboard` の `/healthz` の 1 つだけ。
    assert find_path_literals(service_source) == [HEALTH_PATH]
    assert find_path_literals(load_sources("admin/routers")["admin/routers/dashboard.py"]) == [
        "/dashboard"
    ]


def test_the_opensearch_probe_calls_only_cluster_health_through_the_wrapper() -> None:
    source = load_sources(OPENSEARCH_DIRECTORY)[HEALTH_PROBE_FILE]
    tree = ast.parse(source)

    # 生のクライアントを直接呼ばない(`client` を含む名前の呼び出しがない。(a)(b) が見る)。
    assert find_client_calls(tree) == []
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and ast.unparse(node.func.value) == "self._readonly"
    }
    assert called == {"cluster_health"}


# --- (e) 検出器の自己テスト(合成ソース。負例が空振りしない) ---

OTHER_PROBES_FILE = f"{PROBES_DIRECTORY}/web_dist.py"


@pytest.mark.parametrize(
    "call",
    [
        "self._pool.request('GET', url)",
        "self._pool.request('GET', url, retries=False, redirect=False, preload_content=False)",
    ],
)
def test_a_get_for_the_given_url_is_accepted(call: str) -> None:
    assert find_probe_sends_not_get_of_the_given_url(call) == []
    assert find_probe_sends_outside_http_probe({PROBES_HTTP_FILE: call}) == []


@pytest.mark.parametrize(
    "call",
    [
        "self._pool.request('POST', url)",
        "self._pool.request('PUT', url)",
        "self._pool.request('DELETE', url)",
        "self._pool.request('HEAD', url)",
        "self._pool.request('get', url)",
        "self._pool.request(method, url)",
        "self._pool.request(self._method, url)",
        "self._pool.urlopen('POST', url)",
        "urllib3.request('POST', url)",
        "self._pool.request_encode_body('POST', url)",
    ],
)
def test_a_probe_send_that_is_not_a_get_is_detected(call: str) -> None:
    assert len(find_probe_sends_not_get_of_the_given_url(call)) == 1


@pytest.mark.parametrize(
    "call",
    [
        "self._pool.request('GET', '/healthz')",
        "self._pool.request('GET', f'{base}/healthz')",
        "self._pool.request('GET', self._url)",
        "self._pool.request('GET', url + '/x')",
        "self._pool.request('GET', url, **options)",
        "self._pool.request(*arguments)",
    ],
)
def test_a_probe_send_that_is_not_for_the_given_url_alone_is_detected(call: str) -> None:
    assert find_probe_sends_not_get_of_the_given_url(call) != []


def test_a_probe_send_outside_http_probe_is_detected() -> None:
    problems = find_probe_sends_outside_http_probe(
        {OTHER_PROBES_FILE: "self._pool.request('GET', url)"}
    )

    assert len(problems) == 1
    assert "outside http_probe.py" in problems[0]


def test_two_probe_sends_in_http_probe_are_detected() -> None:
    source = "self._pool.request('GET', url)\nself._pool.request('GET', url)"

    [problem] = find_probe_sends_outside_http_probe({PROBES_HTTP_FILE: source})

    assert "more than one place" in problem


@pytest.mark.parametrize(
    "call",
    [
        "self._pool.request('GET', url, preload_content=True)",
        "self._pool.request('GET', url)",
        "self._pool.request('GET', url, preload_content=preload)",
    ],
)
def test_a_probe_send_that_preloads_the_body_is_detected(call: str) -> None:
    assert len(find_probe_sends_that_read_the_body(call)) == 1


@pytest.mark.parametrize(
    "source",
    [
        "PATH = '/healthz'",
        "url = f'{base}/healthz'",
        "return '/api/status'",
    ],
)
def test_a_path_literal_in_the_probes_is_detected(source: str) -> None:
    assert find_path_literals_in_probes({OTHER_PROBES_FILE: source}) != []


def test_a_probe_without_path_literals_is_accepted() -> None:
    source = "INDEX_FILE_NAME = 'index.html'\nx = Path(directory) / INDEX_FILE_NAME"

    assert find_path_literals_in_probes({OTHER_PROBES_FILE: source}) == []


@pytest.mark.parametrize(
    "signature",
    [
        "def check(self, url, method): ...",
        "def check(self, url, *, headers=None): ...",
        "def check(self, url, *args): ...",
        "def check(self, **kwargs): ...",
        "def check(self): ...",
    ],
)
def test_a_probe_operation_that_does_not_accept_only_the_url_is_detected(signature: str) -> None:
    operation = ast.parse(signature).body[0]
    assert isinstance(operation, ast.FunctionDef)

    assert not accepts_only_the_url(operation)


def test_a_probe_operation_that_accepts_only_the_url_is_accepted() -> None:
    operation = ast.parse("def check(self, url): ...").body[0]
    assert isinstance(operation, ast.FunctionDef)

    assert accepts_only_the_url(operation)
