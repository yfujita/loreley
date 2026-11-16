"""R7(書き込みの範囲)の部分検査。

R7: Crawler が書く索引は `loreley-sources` と `loreley-jobs` だけで、書き込みの呼び出しは
`infrastructure/opensearch` の中に閉じる。検索インデックスと `loreley-deletions` は Indexer だけが
書き、Crawler は指さない(CA-K-2)。

import では検査できないため、OpenSearch クライアントの書き込み呼び出しの場所と、禁止する索引名の
文字列を AST で見る。受け口は、名前に `client` を含む属性チェーン(`client`、`self._client.indices`
など)。動的な呼び出し(`getattr(client, name)(...)` など)や、`client` を含まない名前へ代入し直した
クライアント、`client.transport.perform_request(...)` のような低水準の呼び出しは検出できない。

Repository の中(`infrastructure/opensearch/`)の書き込みは、すべて条件つきであることも検査する
`index` は `op_type`(`create`)か版(`if_seq_no`・`if_primary_term`)を条件にし、`delete` は
版を条件にする。`bulk`(ID のバルク削除)は `bulk_delete.py` だけが使う。`update`・
`update_by_query`・`delete_by_query`・`reindex` と、索引・マッピングの変更は使わない(索引の作成は
`opensearch-init`。CM-K-9)。索引名は設定で与えるので、`loreley-` で始まる文字列を持たない。
どの呼び出しが版を持つ値を渡すか(読んだ版か)は、検査できない(Repository の契約テストで確かめる)。

Repository の呼び出し側(`sources`・`jobs`)の書き込み(P4 で追加): Repository の書き込み操作
(`create`・`replace_if_unchanged`・`delete_if_unchanged`・`delete_ids`)の呼び出しは、`sources/`
(`loreley-sources`)と `jobs/records/`・`jobs/locks/`(`loreley-jobs`)だけに置く。`jobs` 直下や
`crawl` などは Repository を呼ばず、`sources` の読み取りには `SourceReader` を使い、
書き込みの `SourceStore` を import してよいのは `api`・`source_delete`・`main` だけ。版条件つきの
置き換え・削除は、版の引数を定数にしない(読んだ値を渡す)。Repository に版条件なしの書き込み
操作を足せば失敗する。Repository のインスタンスは索引ごとに `main.py` が作って渡すので、
`sources` が `loreley-jobs` を書く(逆も)ことは、この割り当てと import の許可表
(`dependency_rules.py`)の組み合わせで防ぐ。

Repository の呼び出しの検出は、受け口の名前に `repository` を含む属性チェーン(`repository`、
`self._repository` など)に頼る。名前に `repository` を含まない変数への代入し直し
(`store = self._repository; store.create(...)`)や、動的な呼び出しは検出できない(限界)。

`main.py` が作る Repository(P8): Repository の生成(`OpenSearchRepository(...)`)は `main.py` だけが
行い、ちょうど 3 つ — `loreley-sources` 用・`loreley-jobs` 用(Store 層のクライアントを共有)・
ハートビート専用の `loreley-jobs` 用(専用クライアント。CM-P-14)。索引名は設定の
`sources_index_name`・`jobs_index_name` だけで、`loreley-deletions` や検索インデックスを指す
Repository は作らない。クライアントの生成(`create_store_client`・`create_heartbeat_client`)も
`main.py` で 1 回ずつ。生成の検出は呼び出しの名前(`OpenSearchRepository`)に頼るので、別名での
生成や動的な生成は検出できない(限界)。
"""

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from loreley_crawler.infrastructure.opensearch import Repository

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "loreley_crawler"

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
    # `client.indices.*`(索引自体の変更。create/delete は上と共通の名前)。索引・マッピングの
    # 作成は `opensearch-init` が行い、Crawler は作らない(CM-K-9)。
    "put_mapping",
    "put_settings",
    "put_alias",
    "delete_alias",
    "update_aliases",
    "put_index_template",
    "delete_index_template",
}

# クライアントの書き込み呼び出しを置いてよい場所(パッケージルートからの相対パスの接頭辞)。
WRITE_SITE_PREFIX = "infrastructure/opensearch/"

# `bulk`(ID のバルク削除)を使ってよい場所。
BULK_SITE = "infrastructure/opensearch/bulk_delete.py"
VERSION_CONDITIONS = {"if_seq_no", "if_primary_term"}

# Repository の書き込み操作と、その呼び出しを置いてよい場所。
REPOSITORY_WRITE_METHODS = {"create", "replace_if_unchanged", "delete_if_unchanged", "delete_ids"}
VERSIONED_REPOSITORY_METHODS = {"replace_if_unchanged", "delete_if_unchanged"}
REPOSITORY_RECEIVER_MARKER = "repository"
REPOSITORY_WRITE_SITES = ("sources/", "jobs/records/", "jobs/locks/")
EXPECTED_REPOSITORY_OPERATIONS = {
    "fetch",
    "create",
    "replace_if_unchanged",
    "delete_if_unchanged",
    "list_records",
    "scan",
    "delete_ids",
}

# `loreley-sources` に書く `SourceStore`(読み取りは `SourceReader`)を import してよい場所。
SOURCE_STORE_NAME = "SourceStore"
SOURCE_STORE_USER_SITES = ("sources/", "api/", "source_delete/", "main.py")

# Repository・OpenSearch クライアントの生成(R7: `main.py` だけが行う)。
REPOSITORY_FACTORY = "OpenSearchRepository"
CLIENT_FACTORIES = {"create_store_client", "create_heartbeat_client"}
MAIN_PATH = "main.py"
CREATION_SITE_PREFIXES = (MAIN_PATH, "infrastructure/opensearch/")
# `main.py` が作る Repository(クライアント、索引名)。ちょうどこの 3 つ。
EXPECTED_MAIN_REPOSITORIES = [
    ("store_client", "config.sources_index_name"),
    ("store_client", "config.jobs_index_name"),
    ("heartbeat_client", "config.jobs_index_name"),
]

# Crawler が指してはならない索引(Indexer だけが書く。`apps/indexer` の既定の索引名)。
FORBIDDEN_INDEX_NAMES = {"loreley-documents", "loreley-deletions"}


@dataclass(frozen=True)
class WriteCall:
    method: str
    line: int


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
    return [
        WriteCall(node.func.attr, node.lineno)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in WRITE_METHODS
        and is_client_receiver(node.func.value)
    ]


def is_repository_receiver(node: ast.expr) -> bool:
    """`repository`、`self._repository` のように、Repository 由来と読める式か。"""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return False
    parts.append(node.id)
    return any(REPOSITORY_RECEIVER_MARKER in part.lower() for part in parts)


def find_repository_write_calls(source: str) -> list[tuple[ast.Call, str]]:
    """Repository の書き込み操作の呼び出しと、その操作名。"""
    return [
        (node, node.func.attr)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in REPOSITORY_WRITE_METHODS
        and is_repository_receiver(node.func.value)
    ]


def find_misplaced_repository_writes(sources: Mapping[str, str]) -> list[str]:
    """`sources/`・`jobs/records/`・`jobs/locks/` の外にある、Repository の書き込み呼び出し。"""
    return [
        f"{path}:{call.lineno}: repository.{method}(...)"
        for path, source in sorted(sources.items())
        if not path.startswith(REPOSITORY_WRITE_SITES)
        for call, method in find_repository_write_calls(source)
    ]


def find_unversioned_repository_writes(sources: Mapping[str, str]) -> list[str]:
    """版条件つきの置き換え・削除で、版を定数で渡している(読んだ版を条件にしていない)呼び出し。"""
    problems: list[str] = []
    for path, source in sorted(sources.items()):
        for call, method in find_repository_write_calls(source):
            if method not in VERSIONED_REPOSITORY_METHODS:
                continue
            versions = {keyword.arg: keyword.value for keyword in call.keywords}
            for name in ("seq_no", "primary_term"):
                value = versions.get(name)
                if value is None or isinstance(value, ast.Constant):
                    problems.append(f"{path}:{call.lineno}: repository.{method}({name}=...)")
    return problems


def find_source_store_imports_outside_writers(sources: Mapping[str, str]) -> list[str]:
    """`SourceStore`(`loreley-sources` に書く)を、書いてよい場所の外で import している箇所。"""
    return [
        f"{path}:{node.lineno}: imports {SOURCE_STORE_NAME}"
        for path, source in sorted(sources.items())
        if not path.startswith(SOURCE_STORE_USER_SITES)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
        and any(alias.name == SOURCE_STORE_NAME for alias in node.names)
    ]


def find_misplaced_write_calls(sources: Mapping[str, str]) -> list[str]:
    """`infrastructure/opensearch/` の外にあるクライアントの書き込み呼び出し。"""
    return [
        f"{path}:{call.line}: client.{call.method}(...)"
        for path, source in sorted(sources.items())
        if not path.startswith(WRITE_SITE_PREFIX)
        for call in find_write_calls(source)
    ]


def string_literals(source: str) -> list[str]:
    """docstring を除く文字列定数。説明文に索引名を書くことは禁じない(指していないため)。"""
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def find_forbidden_index_names(sources: Mapping[str, str]) -> list[str]:
    return [
        f"{path}: {literal!r}"
        for path, source in sorted(sources.items())
        for literal in string_literals(source)
        if any(name in literal for name in FORBIDDEN_INDEX_NAMES)
    ]


def find_unconditional_writes(sources: Mapping[str, str]) -> list[str]:
    """`infrastructure/opensearch/` の中の、条件のない(または許していない)書き込み呼び出し。"""
    problems: list[str] = []
    for path, source in sorted(sources.items()):
        if not path.startswith(WRITE_SITE_PREFIX):
            continue
        for node in ast.walk(ast.parse(source)):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in WRITE_METHODS
                and is_client_receiver(node.func.value)
            ):
                continue
            method = node.func.attr
            keywords = {keyword.arg for keyword in node.keywords}
            if not _is_allowed_write(path, method, keywords):
                problems.append(f"{path}:{node.lineno}: client.{method}(...)")
    return problems


def _is_allowed_write(path: str, method: str, keywords: set[str | None]) -> bool:
    has_version = keywords >= VERSION_CONDITIONS
    if method == "index":
        return "op_type" in keywords or has_version
    if method == "delete":
        return has_version
    if method == "bulk":
        return path == BULK_SITE
    return False


def find_hardcoded_index_names(sources: Mapping[str, str]) -> list[str]:
    """`infrastructure/opensearch/` の、`loreley-` で始まる文字列(索引名は設定で与える)。"""
    return [
        f"{path}: {literal!r}"
        for path, source in sorted(sources.items())
        if path.startswith(WRITE_SITE_PREFIX)
        for literal in string_literals(source)
        if literal.startswith("loreley-")
    ]


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def find_calls(source: str, names: set[str]) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and _called_name(node) in names
    ]


def find_creations_outside_main(sources: Mapping[str, str]) -> list[str]:
    """Repository・クライアントの生成が、`main.py`(と、それを定義する `infrastructure/opensearch/`)
    以外にある。"""
    return [
        f"{path}:{call.lineno}: {_called_name(call)}(...)"
        for path, source in sorted(sources.items())
        if not path.startswith(CREATION_SITE_PREFIXES)
        for call in find_calls(source, {REPOSITORY_FACTORY, *CLIENT_FACTORIES})
    ]


def main_repositories(source: str) -> list[tuple[str, str]]:
    """`main.py` が作る Repository の (クライアント、索引名)。引数の式を文字列にして返す。"""
    repositories: list[tuple[str, str]] = []
    for call in find_calls(source, {REPOSITORY_FACTORY}):
        client, index_name = call.args[0], call.args[1]
        repositories.append((ast.unparse(client), ast.unparse(index_name)))
    return repositories


def main_client_creations(source: str) -> list[str]:
    return [_called_name(call) or "" for call in find_calls(source, CLIENT_FACTORIES)]


def load_package_sources() -> dict[str, str]:
    return {
        path.relative_to(PACKAGE_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in PACKAGE_ROOT.rglob("*.py")
    }


# --- 実際のソースツリー ---


def test_client_write_calls_exist_only_in_the_opensearch_module() -> None:
    assert find_misplaced_write_calls(load_package_sources()) == []


def test_the_crawler_never_refers_to_the_indexer_owned_indexes() -> None:
    assert find_forbidden_index_names(load_package_sources()) == []


def test_every_write_of_the_repository_is_conditional() -> None:
    assert find_unconditional_writes(load_package_sources()) == []


def test_the_repository_does_not_hardcode_index_names() -> None:
    assert find_hardcoded_index_names(load_package_sources()) == []


def test_repository_writes_exist_only_in_sources_and_the_jobs_records_and_locks() -> None:
    assert find_misplaced_repository_writes(load_package_sources()) == []


def test_every_conditional_repository_write_passes_a_version_that_was_read() -> None:
    assert find_unversioned_repository_writes(load_package_sources()) == []


def test_only_the_source_writers_import_the_source_store() -> None:
    assert find_source_store_imports_outside_writers(load_package_sources()) == []


def test_the_repository_has_no_write_operation_without_a_condition() -> None:
    """版条件も `create` も使わない書き込み(無条件の置き換え・削除)を、Repository に足せない。"""
    assert set(Repository.__abstractmethods__) == EXPECTED_REPOSITORY_OPERATIONS


def test_the_checks_fail_on_violating_files_added_to_the_actual_tree() -> None:
    """検査が実際のツリーに対しても働くこと(現状で成功するだけのテストにしない)。"""
    sources = load_package_sources()
    sources["jobs/records/fake.py"] = (
        "def f(client):\n    client.index(index='i', id='1', body={})\n"
    )
    sources["sources/fake.py"] = "DELETIONS = 'loreley-deletions'\n"

    sources["infrastructure/opensearch/fake.py"] = (
        "def f(client):\n    client.index(index='i', id='1', body={})\n    X = 'loreley-jobs'\n"
    )

    assert find_misplaced_write_calls(sources) == ["jobs/records/fake.py:2: client.index(...)"]
    assert find_forbidden_index_names(sources) == ["sources/fake.py: 'loreley-deletions'"]
    assert find_unconditional_writes(sources) == [
        "infrastructure/opensearch/fake.py:2: client.index(...)"
    ]
    assert find_hardcoded_index_names(sources) == [
        "infrastructure/opensearch/fake.py: 'loreley-jobs'"
    ]


def test_the_repository_checks_fail_on_violating_files_added_to_the_actual_tree() -> None:
    sources = load_package_sources()
    sources["jobs/fake.py"] = "def f(self):\n    self._repository.create('i', {})\n"
    sources["crawl/fake.py"] = (
        "from loreley_crawler.sources import SourceStore\n"
        "def f(repository):\n"
        "    repository.delete_ids([])\n"
    )
    sources["jobs/records/fake.py"] = (
        "def f(repository):\n"
        "    repository.replace_if_unchanged('i', {}, seq_no=1, primary_term=1)\n"
    )

    assert find_misplaced_repository_writes(sources) == [
        "crawl/fake.py:3: repository.delete_ids(...)",
        "jobs/fake.py:2: repository.create(...)",
    ]
    assert find_source_store_imports_outside_writers(sources) == [
        "crawl/fake.py:1: imports SourceStore"
    ]
    assert find_unversioned_repository_writes(sources) == [
        "jobs/records/fake.py:2: repository.replace_if_unchanged(seq_no=...)",
        "jobs/records/fake.py:2: repository.replace_if_unchanged(primary_term=...)",
    ]


# --- 検査器の自己テスト ---


def test_writes_inside_the_opensearch_module_are_allowed() -> None:
    sources = {"infrastructure/opensearch/repository.py": "self._client.index(index='i')\n"}
    assert find_misplaced_write_calls(sources) == []


def test_writes_elsewhere_are_reported_with_the_path_and_line() -> None:
    sources = {
        "jobs/locks/a.py": "x = 1\nself._client.delete(index='i', id='1')\n",
        "infrastructure/indexer_client/a.py": "client.update(index='i')\n",
    }
    assert find_misplaced_write_calls(sources) == [
        "infrastructure/indexer_client/a.py:1: client.update(...)",
        "jobs/locks/a.py:2: client.delete(...)",
    ]


@pytest.mark.parametrize(
    ("call", "method"),
    [
        ("client.index(index='i', id='1', body={})", "index"),
        ("self._client.bulk(body=[])", "bulk"),
        ("client.indices.create(index='i')", "create"),
        ("self._client.indices.put_mapping(index='i', body={})", "put_mapping"),
        ("opensearch_client.indices.put_settings(body={})", "put_settings"),
        ("self.client.indices.delete(index='i')", "delete"),
        ("os_client.reindex(body={})", "reindex"),
        ("client.delete_by_query(index='i', body={})", "delete_by_query"),
    ],
)
def test_detector_finds_writes_through_any_client_attribute(call: str, method: str) -> None:
    assert [found.method for found in find_write_calls(call)] == [method]


@pytest.mark.parametrize(
    "call",
    [
        "client.get(index='i')",
        "client.search(index='i')",
        "client.indices.exists(index='i')",
        "client.indices.refresh(index='i')",  # refresh は書き込みではない(全件走査の前に呼ぶ)
        "cache.create()",
        "other.index(1)",
    ],
)
def test_detector_ignores_reads_and_non_client_receivers(call: str) -> None:
    assert find_write_calls(call) == []


def test_forbidden_index_names_are_found_in_string_constants_only() -> None:
    sources = {
        "a.py": "INDEX = 'loreley-documents'\n",
        "b.py": "INDEX = f'{prefix}-loreley-deletions'\n",
        "c.py": '"""loreley-deletions は Indexer だけが書く。"""\nX = 1\n',
        "d.py": "# loreley-deletions\nclass C:\n    '''loreley-documents'''\n",
        "e.py": "INDEX = 'loreley-jobs'\nOTHER = 'loreley-sources'\n",
    }
    # f 文字列の定数部分も対象。docstring・コメント・別の索引名は対象外。
    assert find_forbidden_index_names(sources) == [
        "a.py: 'loreley-documents'",
        "b.py: '-loreley-deletions'",
    ]


@pytest.mark.parametrize(
    "call",
    [
        "client.index(index='i', id='1', body={}, op_type='create')",
        "client.index(index='i', id='1', body={}, if_seq_no=1, if_primary_term=1)",
        "self._client.delete(index='i', id='1', if_seq_no=1, if_primary_term=1)",
    ],
)
def test_conditional_writes_in_the_repository_are_allowed(call: str) -> None:
    assert find_unconditional_writes({"infrastructure/opensearch/a.py": f"{call}\n"}) == []


@pytest.mark.parametrize(
    "call",
    [
        "client.index(index='i', id='1', body={})",
        "client.index(index='i', id='1', body={}, if_seq_no=1)",  # 版の片方だけ
        "client.delete(index='i', id='1')",
        "client.delete(index='i', id='1', if_seq_no=1)",
        "client.update(index='i', id='1', body={})",
        "client.update_by_query(index='i', body={})",
        "client.delete_by_query(index='i', body={})",
        "client.indices.put_mapping(index='i', body={})",
        "client.indices.create(index='i')",
        "client.bulk(body=[])",  # `bulk_delete.py` の外
    ],
)
def test_unconditional_or_unlisted_writes_in_the_repository_are_found(call: str) -> None:
    sources = {"infrastructure/opensearch/a.py": f"{call}\n"}
    assert len(find_unconditional_writes(sources)) == 1


def test_bulk_is_allowed_only_in_the_bulk_delete_module() -> None:
    sources = {
        "infrastructure/opensearch/bulk_delete.py": "client.bulk(body=[])\n",
        "infrastructure/opensearch/other.py": "client.bulk(body=[])\n",
    }
    assert find_unconditional_writes(sources) == [
        "infrastructure/opensearch/other.py:1: client.bulk(...)"
    ]


def test_writes_outside_the_repository_are_left_to_the_placement_check() -> None:
    # 置き場所の違反は `find_misplaced_write_calls` が報告する。ここでは二重に数えない。
    assert find_unconditional_writes({"jobs/records/a.py": "client.index(index='i')\n"}) == []


# --- Repository 呼び出しの検査器の自己テスト ---


@pytest.mark.parametrize(
    "call",
    [
        "repository.create('i', {})",
        "self._repository.replace_if_unchanged('i', {}, seq_no=a, primary_term=b)",
        "self._lock_repository.delete_if_unchanged('i', seq_no=a, primary_term=b)",
        "jobs_repository.delete_ids(ids)",
    ],
)
def test_repository_writes_are_found_through_any_repository_attribute(call: str) -> None:
    assert len(find_misplaced_repository_writes({"crawl/a.py": f"{call}\n"})) == 1


@pytest.mark.parametrize(
    "call",
    [
        "repository.fetch('i')",
        "repository.scan(f, sort=s)",
        "repository.list_records(f, s, limit=1)",
        "connector_type.create(source_id, config)",  # Repository ではない `create`
        "cache.delete_ids(ids)",
    ],
)
def test_reads_and_other_receivers_are_not_repository_writes(call: str) -> None:
    assert find_misplaced_repository_writes({"crawl/a.py": f"{call}\n"}) == []


@pytest.mark.parametrize("path", ["sources/a.py", "jobs/records/a.py", "jobs/locks/a.py"])
def test_the_allowed_sites_may_write_through_a_repository(path: str) -> None:
    assert find_misplaced_repository_writes({path: "repository.create('i', {})\n"}) == []


@pytest.mark.parametrize(
    "path", ["jobs/a.py", "jobs/job_runner.py", "api/a.py", "scheduler/a.py", "source_delete/a.py"]
)
def test_other_modules_including_the_jobs_top_level_may_not_write_through_a_repository(
    path: str,
) -> None:
    assert len(find_misplaced_repository_writes({path: "repository.create('i', {})\n"})) == 1


@pytest.mark.parametrize(
    "call",
    [
        "repository.replace_if_unchanged('i', b, seq_no=1, primary_term=stored.primary_term)",
        "repository.replace_if_unchanged('i', b, seq_no=stored.seq_no, primary_term=None)",
        "repository.delete_if_unchanged('i', seq_no=stored.seq_no)",  # 版の片方がない
        "repository.delete_if_unchanged('i')",
    ],
)
def test_a_constant_or_missing_version_is_not_a_version_that_was_read(call: str) -> None:
    assert len(find_unversioned_repository_writes({"sources/a.py": f"{call}\n"})) >= 1


def test_versions_taken_from_what_was_read_pass() -> None:
    sources = {
        "sources/a.py": (
            "self._repository.replace_if_unchanged(\n"
            "    record_id, body, seq_no=stored.seq_no, primary_term=stored.primary_term)\n"
            "repository.delete_if_unchanged(i, seq_no=current.seq_no, primary_term=current.pt)\n"
        )
    }
    assert find_unversioned_repository_writes(sources) == []


def test_creates_and_bulk_deletes_need_no_version() -> None:
    sources = {"sources/a.py": "repository.create('i', {})\nrepository.delete_ids(ids)\n"}
    assert find_unversioned_repository_writes(sources) == []


@pytest.mark.parametrize("path", ["api/a.py", "source_delete/a.py", "sources/a.py", "main.py"])
def test_the_source_writers_may_import_the_source_store(path: str) -> None:
    source = "from loreley_crawler.sources import SourceStore\n"
    assert find_source_store_imports_outside_writers({path: source}) == []


@pytest.mark.parametrize("path", ["jobs/a.py", "scheduler/a.py", "crawl/a.py", "jobs/records/a.py"])
def test_the_readers_of_sources_may_not_import_the_source_store(path: str) -> None:
    source = "from loreley_crawler.sources import SourceReader, SourceStore\n"
    assert find_source_store_imports_outside_writers({path: source}) == [
        f"{path}:1: imports SourceStore"
    ]
    assert (
        find_source_store_imports_outside_writers(
            {path: "from loreley_crawler.sources import SourceReader\n"}
        )
        == []
    )


# --- main.py が作る Repository は 3 つだけ(R7。P8) ---


def test_repositories_and_clients_are_created_only_in_main() -> None:
    assert find_creations_outside_main(load_package_sources()) == []


def test_main_creates_exactly_the_three_repositories_on_the_expected_indexes_and_clients() -> None:
    main_source = load_package_sources()[MAIN_PATH]

    assert main_repositories(main_source) == EXPECTED_MAIN_REPOSITORIES


def test_main_creates_one_store_client_and_one_heartbeat_client() -> None:
    main_source = load_package_sources()[MAIN_PATH]

    assert sorted(main_client_creations(main_source)) == [
        "create_heartbeat_client",
        "create_store_client",
    ]


def test_the_creation_checks_fail_on_violating_files_added_to_the_actual_tree() -> None:
    sources = load_package_sources()
    sources["jobs/fake.py"] = "def f(client, c):\n    return OpenSearchRepository(client, 'i', c)\n"
    sources["crawl/fake.py"] = "import opensearch as o\nx = o.create_store_client(config)\n"

    assert find_creations_outside_main(sources) == [
        "crawl/fake.py:2: create_store_client(...)",
        "jobs/fake.py:2: OpenSearchRepository(...)",
    ]


MAIN_WITH_FOUR_REPOSITORIES = """
def create_backends(config):
    store_client = create_store_client(config.opensearch)
    heartbeat_client = create_heartbeat_client(config.opensearch)
    OpenSearchRepository(store_client, config.sources_index_name)
    OpenSearchRepository(store_client, config.jobs_index_name)
    OpenSearchRepository(heartbeat_client, config.jobs_index_name)
    mod.OpenSearchRepository(store_client, config.deletions_index_name)
"""


def test_a_fourth_repository_or_one_on_another_index_in_main_is_detected() -> None:
    repositories = main_repositories(MAIN_WITH_FOUR_REPOSITORIES)

    assert len(repositories) == 4
    assert repositories != EXPECTED_MAIN_REPOSITORIES
    assert repositories[:3] == EXPECTED_MAIN_REPOSITORIES
    assert repositories[3] == ("store_client", "config.deletions_index_name")


def test_a_heartbeat_repository_on_the_store_client_is_detected() -> None:
    source = MAIN_WITH_FOUR_REPOSITORIES.replace(
        "OpenSearchRepository(heartbeat_client, config.jobs_index_name)",
        "OpenSearchRepository(store_client, config.jobs_index_name)",
    )

    assert ("heartbeat_client", "config.jobs_index_name") not in main_repositories(source)


def test_creations_inside_the_opensearch_module_and_main_are_allowed() -> None:
    sources = {
        "main.py": MAIN_WITH_FOUR_REPOSITORIES,
        "infrastructure/opensearch/connection.py": "def f(c):\n    return create_store_client(c)\n",
    }

    assert find_creations_outside_main(sources) == []
