"""依存ルール R1〜R6・R10(module 6章)のうち、import で検査できるものの検査器。

ファイルを「モジュール」に分類し、許可した import だけを通す。許可表(ALLOWED)が
ルールの実体で、各行に根拠のルール番号を書く。検査は AST で行い、import 文を実行しない。
関数内・`TYPE_CHECKING` 内・`try` 内の import も検査する。

module-structure 3章のディレクトリ構成のすべて(まだ実装がないものを含む)を分類できるので、
後続のフェーズでファイルが増えても、許可表にない import は違反になる。

制約: import 文だけが対象で、動的な import(`importlib.import_module`、`__import__`、
文字列から組み立てたモジュール名)は検出できない。R7(書き込み)は `test_write_rules.py`、
R8・R9・R11 は import の検査の対象外で、各機能のテストで確認する。
"""

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

PACKAGE = "loreley_crawler"

# 常にどのモジュールからも import してよい(R10: 共通部品。`common` は葉で、誰にも依存しない)。
COMMON = "common"

# モジュール → import してよいモジュール(自分自身と `common` は常に許可)。
# 層の順: 入口層(api・scheduler)→ アプリケーション機能 → infrastructure(R1)。
ALLOWED: dict[str, frozenset[str]] = {
    # R4: api・scheduler は形式の検証と受け渡し・起動時刻の判定だけ。依存先は jobs と sources のみ
    # (crawl・source_delete・connectors・infrastructure は import しない)。
    "api": frozenset({"jobs", "sources"}),
    "scheduler": frozenset({"jobs", "sources"}),
    # R3: アプリケーション機能どうしの依存は 9 本だけ。
    #   jobs → sources、crawl → jobs・sources・documents・connectors、
    #   source_delete → jobs・sources、sources → connectors、documents → connectors。
    # jobs は crawl・source_delete を import しない(実行対象は main が注入する)。
    # R6: jobs の内部は、直下 → records・locks。records と locks は互いに依存しない。
    "jobs": frozenset({"jobs.records", "jobs.locks", "sources", "infrastructure.opensearch"}),
    "jobs.records": frozenset({"infrastructure.opensearch"}),
    "jobs.locks": frozenset({"infrastructure.opensearch"}),
    "sources": frozenset({"connectors", "connectors.interface", "infrastructure.opensearch"}),
    "crawl": frozenset(
        {
            "jobs",
            "sources",
            "documents",
            "connectors",
            "connectors.interface",
            "infrastructure.indexer_client",
        }
    ),
    "source_delete": frozenset({"jobs", "sources", "infrastructure.indexer_client"}),
    # documents → connectors は interface/ の型と変換関数だけ(module 4.7)。
    "documents": frozenset({"connectors.interface"}),
    # R5: connectors は opensearch・indexer_client と他の機能に依存しない(葉)。
    # 内部は、直下(レジストリ)→ filesystem → interface の一方向で、interface は他に依存しない。
    # MVP の FS は infrastructure を使わない(R2)ので、infrastructure は 1 つも許可しない。
    "connectors": frozenset({"connectors.filesystem", "connectors.interface"}),
    "connectors.filesystem": frozenset({"connectors.interface"}),
    "connectors.interface": frozenset(),
    # R2・R5: 外部システムへのアクセスは infrastructure に限る。infrastructure どうしも依存しない。
    "infrastructure.opensearch": frozenset(),
    "infrastructure.indexer_client": frozenset(),
    # main.py は Composition Root(組み立て。module 3章)。config を使い、全モジュールを組み立てる。
    "main": frozenset(
        {
            "config",
            "api",
            "scheduler",
            "sources",
            "jobs",
            "jobs.records",
            "jobs.locks",
            "crawl",
            "source_delete",
            "documents",
            "connectors",
            "connectors.interface",
            "connectors.filesystem",
            "infrastructure.opensearch",
            "infrastructure.indexer_client",
        }
    ),
    # config.py は、値を各モジュールの設定 dataclass に詰めて main に渡す(module 3章)ため、
    # その dataclass を持つモジュールの入口だけを import する(内部のモジュールには触れない)。
    # どのモジュールも config に依存しないので、config からの依存が循環を作らない。
    # `config.py` は、`jobs`(`JobsSettings`・`HeartbeatSettings`)、`crawl`、`documents`、
    # `scheduler`、`connectors`(`FileSystemSettings`)、`infrastructure` の設定型を import する。
    "config": frozenset(
        {
            "api",
            "scheduler",
            "sources",
            "jobs",
            "crawl",
            "source_delete",
            "documents",
            "connectors",
            "infrastructure.opensearch",
            "infrastructure.indexer_client",
        }
    ),
    # 名前空間だけのパッケージ(`__init__.py`)。何も import しない。
    "namespace": frozenset(),
    # R10: common は葉。
    COMMON: frozenset(),
}

# R2: 外部システムに接続するライブラリは、infrastructure の該当モジュールだけが import する。
# - OpenSearch(opensearch-py)は `opensearch` だけ。
# - Indexer の HTTP クライアントは urllib3(CM-U-2。実装時に選定)で、`indexer_client` だけ。
#   `opensearch` は opensearch-py の例外・クライアントで足りるので、urllib3 を直接使わない。
# - 選ばなかった HTTP クライアントは、どのモジュールも import しない(空の集合)。
#   `httpx2` は TestClient 用の dev 依存で、テストだけが使う(`tests/` はこの検査の対象外)。
EXTERNAL_LIBRARY_OWNERS: dict[str, frozenset[str]] = {
    "opensearchpy": frozenset({"infrastructure.opensearch"}),
    "urllib3": frozenset({"infrastructure.indexer_client"}),
    "httpx": frozenset(),
    "httpx2": frozenset(),
    "requests": frozenset(),
    "aiohttp": frozenset(),
}

# 子のモジュールを持つ最上位のパッケージ → 子の名前。
_SUB_MODULES: dict[str, set[str]] = {
    "jobs": {"records", "locks"},
    "connectors": {"interface", "filesystem"},
    "infrastructure": {"opensearch", "indexer_client"},
}
_SINGLE_MODULES = {
    "main",
    "config",
    "api",
    "scheduler",
    "sources",
    "crawl",
    "source_delete",
    "documents",
    COMMON,
}


@dataclass(frozen=True)
class Violation:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def module_of(dotted: str) -> str | None:
    """パッケージからの相対のドット名(例: `jobs.records.jobs`)を、モジュール名にする。

    分類できなければ None(未知のディレクトリ・ファイルは、ルールの更新を促すため違反にする)。
    """
    parts = dotted.split(".") if dotted else []
    if not parts:
        return "namespace"
    top = parts[0]
    if top in _SINGLE_MODULES:
        return top
    if top not in _SUB_MODULES:
        return None
    if top == "infrastructure":
        if len(parts) == 1:
            return "namespace"
        return f"infrastructure.{parts[1]}" if parts[1] in _SUB_MODULES[top] else None
    if len(parts) > 1 and parts[1] in _SUB_MODULES[top]:
        return f"{top}.{parts[1]}"
    return top


def dotted_name_of_file(relative_path: str) -> str:
    """`jobs/records/jobs.py` → `jobs.records.jobs`。`__init__.py` はパッケージ名になる。"""
    path = PurePosixPath(relative_path)
    parts = list(path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def find_violations(sources: Mapping[str, str]) -> list[Violation]:
    """`sources`: パッケージルートからの相対パス(`/` 区切り) → ソース。"""
    known_dotted_names = _known_dotted_names(sources)
    violations: list[Violation] = []
    for path, source in sorted(sources.items()):
        dotted = dotted_name_of_file(path)
        own_module = module_of(dotted)
        if own_module is None:
            violations.append(Violation(path, "unclassified file (update dependency rules)"))
            continue
        is_package = PurePosixPath(path).name == "__init__.py"
        for imported in _internal_imports(source, dotted, is_package, known_dotted_names):
            violations += _check_internal_import(path, own_module, imported)
        violations += _check_external_imports(path, own_module, source)
    return violations


def find_cycles(sources: Mapping[str, str]) -> list[list[str]]:
    """モジュール間の import グラフの循環(R1。循環させない)。"""
    known_dotted_names = _known_dotted_names(sources)
    graph: dict[str, set[str]] = {}
    for path, source in sources.items():
        dotted = dotted_name_of_file(path)
        own_module = module_of(dotted)
        if own_module is None:
            continue
        is_package = PurePosixPath(path).name == "__init__.py"
        targets = {
            module_of(imported)
            for imported in _internal_imports(source, dotted, is_package, known_dotted_names)
        }
        graph.setdefault(own_module, set()).update(
            t for t in targets if t is not None and t != own_module
        )
    return _cycles_in(graph)


def _known_dotted_names(sources: Mapping[str, str]) -> set[str]:
    names: set[str] = set()
    for path in sources:
        dotted = dotted_name_of_file(path)
        parts = dotted.split(".") if dotted else []
        names.update(".".join(parts[:i]) for i in range(1, len(parts) + 1))
    return names


def _internal_imports(
    source: str, own_dotted: str, is_package: bool, known_dotted_names: set[str]
) -> list[str]:
    """パッケージ内への import を、パッケージからの相対のドット名で返す。"""
    imported: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                relative = _strip_package(alias.name)
                if relative is not None:
                    imported.append(relative)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from_base(node, own_dotted, is_package)
            if base is None:
                continue
            for alias in node.names:
                candidate = f"{base}.{alias.name}" if base else alias.name
                # `from pkg import name` の name がサブモジュールなら、そのモジュールへの依存。
                imported.append(candidate if candidate in known_dotted_names else base)
    return imported


def _strip_package(module_name: str) -> str | None:
    if module_name == PACKAGE:
        return ""
    if module_name.startswith(f"{PACKAGE}."):
        return module_name[len(PACKAGE) + 1 :]
    return None


def _resolve_from_base(node: ast.ImportFrom, own_dotted: str, is_package: bool) -> str | None:
    if node.level == 0:
        return _strip_package(node.module or "")
    own_parts = own_dotted.split(".") if own_dotted else []
    package_parts = own_parts if is_package else own_parts[:-1]
    keep = len(package_parts) - (node.level - 1)
    base_parts = package_parts[: max(keep, 0)]
    if node.module:
        base_parts += node.module.split(".")
    return ".".join(base_parts)


def _check_internal_import(path: str, own_module: str, imported: str) -> list[Violation]:
    target_module = module_of(imported)
    if target_module is None:
        return [Violation(path, f"imports unclassified module {imported!r}")]
    if target_module in {own_module, COMMON}:
        return []
    if target_module in ALLOWED[own_module]:
        return []
    return [
        Violation(
            path,
            f"{own_module} must not import {target_module} (imports {imported!r}; "
            f"allowed: {sorted(ALLOWED[own_module] | {COMMON}) or 'none'})",
        )
    ]


def _check_external_imports(path: str, own_module: str, source: str) -> list[Violation]:
    violations: list[Violation] = []
    for node in ast.walk(ast.parse(source)):
        top_level_names: list[str] = []
        if isinstance(node, ast.Import):
            top_level_names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            top_level_names = [node.module.split(".")[0]]
        for name in top_level_names:
            owners = EXTERNAL_LIBRARY_OWNERS.get(name)
            if owners is not None and own_module not in owners:
                violations.append(
                    Violation(
                        path,
                        f"{own_module} must not import {name} "
                        f"(external access is limited to {sorted(owners)})",
                    )
                )
    return violations


def _cycles_in(graph: Mapping[str, set[str]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    visiting: list[str] = []
    done: set[str] = set()

    def visit(module: str) -> None:
        if module in done:
            return
        if module in visiting:
            cycles.append([*visiting[visiting.index(module) :], module])
            return
        visiting.append(module)
        for target in sorted(graph.get(module, ())):
            visit(target)
        visiting.pop()
        done.add(module)

    for module in sorted(graph):
        visit(module)
    return cycles
