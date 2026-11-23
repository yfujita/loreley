"""依存ルール(0002 3.2。module 6章 R1〜R5・R12 のうち基盤に当てはまるもの)の検査器。

ファイルを「モジュール」に分類し、許可した import だけを通す。許可表(`build_allowed`)が
ルールの実体。検査は AST で行い、import 文を実行しない。関数内・`TYPE_CHECKING` 内・`try` 内の
import も検査する。

機能パッケージ(`health`、将来の `admin`・`search`・`mcp`)は `FEATURE_PACKAGES` に足す。足すと
許可表に行ができ、`main` だけがその入口を import できる。機能パッケージどうしと `server` は、
機能パッケージを import できない(R2・R3)。

制約: import 文だけが対象で、動的な import(`importlib.import_module`、`__import__`、
文字列から組み立てたモジュール名)は検出できない。
"""

import ast
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

PACKAGE = "loreley_api"

FEATURE_PACKAGES: frozenset[str] = frozenset({"health"})

# 常にどのモジュールからも import してよい(R12: 共通部品。`common` は葉で、誰にも依存しない)。
COMMON = "common"

# 機能以外のモジュール。`__init__.py` だけの名前空間は "namespace"。
SERVER = "server"
MAIN = "main"
CONFIG = "config"
NAMESPACE = "namespace"

# 基盤は、外部システムへ接続するライブラリを使わない。所有者(import してよいモジュール)は
# 空。admin を導入するときに、D の R5 のとおり所有者を割り当てる。
# ただし、ここで検査するのは `src` 配下だけで、テストコードの httpx2(TestClient)は対象外。
EXTERNAL_LIBRARY_OWNERS: dict[str, frozenset[str]] = {
    name: frozenset()
    for name in ("opensearchpy", "urllib3", "requests", "httpx", "httpx2", "aiohttp", "anyio")
}


def build_allowed(
    feature_packages: Collection[str] = FEATURE_PACKAGES,
) -> dict[str, frozenset[str]]:
    """モジュール → import してよいモジュール(自分自身と `common` は常に許可)。"""
    allowed: dict[str, frozenset[str]] = {
        # `main` は組み立てる側。設定・口(server)・すべての機能の入口を import してよい(R1)。
        MAIN: frozenset({CONFIG, SERVER, *feature_packages}),
        # config は値を持つだけで、他のモジュールの型を使わない。どのモジュールも config に
        # 依存しない(main だけが config を使う)。
        CONFIG: frozenset(),
        # R3: server は汎用の口で、機能パッケージの入口を import しない(main が渡す)。
        SERVER: frozenset(),
        # 名前空間だけのパッケージ(`__init__.py`)。何も import しない。
        NAMESPACE: frozenset(),
        # R12: common は葉。
        COMMON: frozenset(),
    }
    # R2: 機能パッケージどうしは依存しない。
    for feature in feature_packages:
        allowed[feature] = frozenset()
    return allowed


@dataclass(frozen=True)
class Violation:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def module_of(dotted: str, feature_packages: Collection[str] = FEATURE_PACKAGES) -> str | None:
    """パッケージからの相対のドット名(例: `health.router`)を、モジュール名にする。

    各モジュールは、トップレベルのパッケージ(またはファイル)1つが単位。サブパッケージは
    親のモジュールに含む。分類できなければ None(未知のディレクトリ・ファイルは、ルールの更新を
    促すため違反にする)。
    """
    parts = dotted.split(".") if dotted else []
    if not parts:
        return NAMESPACE
    top = parts[0]
    if top in {MAIN, CONFIG, SERVER, COMMON, *feature_packages}:
        return top
    return None


def dotted_name_of_file(relative_path: str) -> str:
    """`common/http/errors.py` → `common.http.errors`。

    `__init__.py` はパッケージ名になる。
    """
    path = PurePosixPath(relative_path)
    parts = list(path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def find_violations(
    sources: Mapping[str, str], feature_packages: Collection[str] = FEATURE_PACKAGES
) -> list[Violation]:
    """`sources`: パッケージルートからの相対パス(`/` 区切り) → ソース。"""
    allowed = build_allowed(feature_packages)
    known_dotted_names = _known_dotted_names(sources)
    violations: list[Violation] = []
    for path, source in sorted(sources.items()):
        dotted = dotted_name_of_file(path)
        own_module = module_of(dotted, feature_packages)
        if own_module is None:
            violations.append(Violation(path, "unclassified file (update dependency rules)"))
            continue
        is_package = PurePosixPath(path).name == "__init__.py"
        for imported in _internal_imports(source, dotted, is_package, known_dotted_names):
            violations += _check_internal_import(
                path, own_module, imported, allowed, feature_packages
            )
        violations += _check_external_imports(path, own_module, source)
    return violations


def find_cycles(
    sources: Mapping[str, str], feature_packages: Collection[str] = FEATURE_PACKAGES
) -> list[list[str]]:
    """モジュール間の import グラフの循環(R1。循環させない)。"""
    known_dotted_names = _known_dotted_names(sources)
    graph: dict[str, set[str]] = {}
    for path, source in sources.items():
        dotted = dotted_name_of_file(path)
        own_module = module_of(dotted, feature_packages)
        if own_module is None:
            continue
        is_package = PurePosixPath(path).name == "__init__.py"
        targets = {
            module_of(imported, feature_packages)
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


def _check_internal_import(
    path: str,
    own_module: str,
    imported: str,
    allowed: Mapping[str, frozenset[str]],
    feature_packages: Collection[str],
) -> list[Violation]:
    target_module = module_of(imported, feature_packages)
    if target_module is None:
        return [Violation(path, f"imports unclassified module {imported!r}")]
    if target_module in {own_module, COMMON}:
        return []
    if target_module in allowed[own_module]:
        return []
    return [
        Violation(
            path,
            f"{own_module} must not import {target_module} (imports {imported!r}; "
            f"allowed: {sorted(allowed[own_module] | {COMMON}) or 'none'})",
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
                        f"(external access is limited to {sorted(owners) or 'no module'})",
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
