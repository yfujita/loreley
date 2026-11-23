"""依存ルール(D 6章 R1〜R6・R12 の import で検査できるもの)の検査器。

ファイルを「モジュール」に分類し、許可した import だけを通す。許可表(`build_allowed`)が
ルールの実体。検査は AST で行い、import 文を実行しない。関数内・`TYPE_CHECKING` 内・`try` 内の
import も検査する。

モジュールの単位は、トップレベルのパッケージ(またはファイル)が基本。ただし `admin` は内部の
サブパッケージ(`admin.routers` など。R4)、`infrastructure` は 3 つのモジュール
(`infrastructure.opensearch` など。R6)が単位。`admin` 直下のファイル(`app.py` など)は `admin`。

機能パッケージ(`health`・`admin`、将来の `search`・`mcp`)は `FEATURE_PACKAGES` に足す。足すと
許可表に行ができ、`main` だけがその入口を import できる。機能パッケージどうしと `server` は、
機能パッケージを import できない(R2・R3)。

制約: import 文だけが対象で、動的な import(`importlib.import_module`、`__import__`、
文字列から組み立てたモジュール名)は検出できない。R6 の「`admin` が `infrastructure` から import
するのは Protocol と型だけ」は機械検査できない(慣習)。
"""

import ast
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

PACKAGE = "loreley_api"

FEATURE_PACKAGES: frozenset[str] = frozenset({"health", "admin"})

# 常にどのモジュールからも import してよい(R12: 共通部品。`common` は葉で、誰にも依存しない)。
COMMON = "common"

# 機能以外のモジュール。`__init__.py` だけの名前空間は "namespace"。
SERVER = "server"
MAIN = "main"
CONFIG = "config"
NAMESPACE = "namespace"

ADMIN = "admin"
# `admin` の内部のサブパッケージ(R4)。`admin/` 直下のファイルは `admin` 自身。
ADMIN_SUBMODULES: tuple[str, ...] = (
    "routers",
    "services",
    "schemas",
    "base",
    "derivation",
    "crawler_mapping",
    "failures",
)
# `admin/` 直下に置いてよいファイル(入口。`admin/__init__.py` も含む)。
ADMIN_DIRECT_FILES: frozenset[str] = frozenset(
    {"app", "dependencies", "settings", "openapi_export"}
)
INFRASTRUCTURE = "infrastructure"
OPENSEARCH = "infrastructure.opensearch"
CRAWLER_CLIENT = "infrastructure.crawler_client"
PROBES = "infrastructure.probes"
INFRASTRUCTURE_MODULES: tuple[str, ...] = (OPENSEARCH, CRAWLER_CLIENT, PROBES)


def admin_module(name: str) -> str:
    return f"{ADMIN}.{name}"


@dataclass(frozen=True)
class LibraryOwners:
    """外部ライブラリを import してよい場所。`modules` に加えて、個別のファイルも許す。"""

    modules: frozenset[str] = frozenset()
    # パッケージルートからの相対パス(`/` 区切り)。モジュール単位では広すぎる例外のため。
    files: frozenset[str] = frozenset()

    def describe(self) -> list[str]:
        return sorted(self.modules | self.files)


# R5: 外部システム用ライブラリの所有者。キーは import するドット名の接頭辞で、長く一致したものが
# 使われる(`urllib3.exceptions` は、`urllib3` より優先される)。
# - `urllib3.exceptions` の型だけは、OpenSearch の例外の分類(`ConnectionError.info` の型の判定)に
#   使うので、`infrastructure.opensearch` の 2 ファイルにも許す。`PoolManager` などは許さない。
# - `anyio` は `common/concurrency.py` だけ(`common` 全体には許さない)。
# - 選ばなかった HTTP クライアントは、どこも import しない。`httpx2` は TestClient 用の dev 依存で、
#   テストだけが使う(ここで検査するのは `src` 配下だけ)。
EXTERNAL_LIBRARY_OWNERS: dict[str, LibraryOwners] = {
    "opensearchpy": LibraryOwners(modules=frozenset({OPENSEARCH})),
    "urllib3": LibraryOwners(modules=frozenset({CRAWLER_CLIENT, PROBES})),
    "urllib3.exceptions": LibraryOwners(
        modules=frozenset({CRAWLER_CLIENT, PROBES}),
        files=frozenset(
            {"infrastructure/opensearch/failure.py", "infrastructure/opensearch/health_probe.py"}
        ),
    ),
    "anyio": LibraryOwners(files=frozenset({"common/concurrency.py"})),
    "requests": LibraryOwners(),
    "httpx": LibraryOwners(),
    "httpx2": LibraryOwners(),
    "aiohttp": LibraryOwners(),
}

# R5: `infrastructure` は HTTP の枠組み(`fastapi`・`starlette`)を import しない。
# `common.http` 経由の間接 import も、`_check_internal_import` が禁じる(R12)。
LIBRARIES_FORBIDDEN_IN_INFRASTRUCTURE: frozenset[str] = frozenset({"fastapi", "starlette"})


def build_allowed(
    feature_packages: Collection[str] = FEATURE_PACKAGES,
) -> dict[str, frozenset[str]]:
    """モジュール → import してよいモジュール(自分自身と `common` は常に許可)。"""
    infrastructure = frozenset(INFRASTRUCTURE_MODULES)
    allowed: dict[str, frozenset[str]] = {
        # `main` は組み立てる側。設定・口(server)・すべての機能の入口・infrastructure の
        # 生成の入口を import してよい(R1・R6)。
        MAIN: frozenset({CONFIG, SERVER, *feature_packages, *infrastructure}),
        # config は、値を各モジュールの設定 dataclass に詰めるため、設定型を持つモジュールの入口
        # (`admin`・`infrastructure.*`)だけを import する。どのモジュールも config に依存しない
        # (main だけが config を使う)ので、循環しない。
        CONFIG: frozenset({ADMIN, *infrastructure}),
        # R3: server は汎用の口で、機能パッケージの入口を import しない(main が渡す)。
        SERVER: frozenset(),
        # 名前空間だけのパッケージ(`__init__.py`)。何も import しない。
        NAMESPACE: frozenset(),
        # R12: common は葉。
        COMMON: frozenset(),
        # R4: admin の内部は一方向。routers は infrastructure・derivation を import しない。
        # derivation・failures・schemas・crawler_mapping は base に、base は common だけに依存する。
        # `admin`(直下)・services が infrastructure から import するのは Protocol と型だけ(慣習)。
        ADMIN: frozenset(
            {
                admin_module("routers"),
                admin_module("services"),
                admin_module("schemas"),
                admin_module("base"),
                *infrastructure,
            }
        ),
        admin_module("routers"): frozenset(
            {admin_module("services"), admin_module("schemas"), admin_module("base")}
        ),
        admin_module("services"): frozenset(
            {
                admin_module("derivation"),
                admin_module("crawler_mapping"),
                admin_module("failures"),
                admin_module("schemas"),
                admin_module("base"),
                *infrastructure,
            }
        ),
        admin_module("crawler_mapping"): frozenset({admin_module("base"), CRAWLER_CLIENT}),
        admin_module("failures"): frozenset({admin_module("base")}),
        admin_module("derivation"): frozenset({admin_module("base")}),
        admin_module("schemas"): frozenset({admin_module("base")}),
        admin_module("base"): frozenset(),
        # R6: infrastructure の 3 モジュールは互いに依存しない(共有する型は common)。
        **{module: frozenset() for module in INFRASTRUCTURE_MODULES},
    }
    # R2: 機能パッケージどうしは依存しない(許可表に行がなければ、何も import できない)。
    for feature in feature_packages:
        allowed.setdefault(feature, frozenset())
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
    親のモジュールに含む。ただし `admin` の内部と `infrastructure` は、サブパッケージが単位
    (`admin.routers`、`infrastructure.opensearch`)。分類できなければ None(未知のディレクトリ・
    ファイルは、ルールの更新を促すため違反にする)。
    """
    parts = dotted.split(".") if dotted else []
    if not parts:
        return NAMESPACE
    top = parts[0]
    if top == INFRASTRUCTURE:
        return _infrastructure_module_of(parts)
    if top == ADMIN and ADMIN in feature_packages:
        return _admin_module_of(parts)
    if top in {MAIN, CONFIG, SERVER, COMMON, *feature_packages}:
        return top
    return None


def _infrastructure_module_of(parts: list[str]) -> str | None:
    if len(parts) == 1:
        return NAMESPACE
    module = f"{INFRASTRUCTURE}.{parts[1]}"
    return module if module in INFRASTRUCTURE_MODULES else None


def _admin_module_of(parts: list[str]) -> str | None:
    if len(parts) == 1:
        return ADMIN
    if parts[1] in ADMIN_SUBMODULES:
        return admin_module(parts[1])
    # 直下のファイルは、2 要素のドット名(`admin.app`)。ディレクトリ(`admin.unknown.x`)は分類しない。
    if len(parts) == 2 and parts[1] in ADMIN_DIRECT_FILES:
        return ADMIN
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


def absolute_base_of_from_import(node: ast.ImportFrom, relative_path: str) -> str:
    """`from X import ...` の `X` を、`loreley_api` から始まる絶対のドット名で返す。

    相対 import(`from ...common import clock`)は、import したファイルの位置
    (`relative_path`。パッケージからの相対)から解決する。
    """
    if node.level == 0:
        return node.module or ""
    is_package = PurePosixPath(relative_path).name == "__init__.py"
    base = _resolve_from_base(node, dotted_name_of_file(relative_path), is_package)
    return f"{PACKAGE}.{base}" if base else PACKAGE


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
    # R12: infrastructure は `common.http` を import しない(`fastapi`・`starlette` を間接的に引く)。
    # `common` の他の部品(`results`・`clock` など)は import してよい。
    if own_module in INFRASTRUCTURE_MODULES and _is_common_http(imported):
        return [
            Violation(
                path,
                f"{own_module} must not import common.http (imports {imported!r}; "
                "it pulls in fastapi and starlette)",
            )
        ]
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


def _is_common_http(imported: str) -> bool:
    return imported == f"{COMMON}.http" or imported.startswith(f"{COMMON}.http.")


def _check_external_imports(path: str, own_module: str, source: str) -> list[Violation]:
    violations: list[Violation] = []
    for node in ast.walk(ast.parse(source)):
        for name in _external_import_names(node):
            violations += _check_external_name(path, own_module, name)
    return violations


def _external_import_names(node: ast.AST) -> list[str]:
    """import 文が取り込むもののドット名。`from a.b import c` は `a.b.c`(`*` は `a.b`)。

    `from urllib3 import exceptions` が `urllib3.exceptions` として判定されるように、
    `from` の名前は 1 つずつ結合する。
    """
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return [
            node.module if alias.name == "*" else f"{node.module}.{alias.name}"
            for alias in node.names
        ]
    return []


def _check_external_name(path: str, own_module: str, name: str) -> list[Violation]:
    violations: list[Violation] = []
    top_level_name = name.split(".")[0]
    if own_module in INFRASTRUCTURE_MODULES and top_level_name in (
        LIBRARIES_FORBIDDEN_IN_INFRASTRUCTURE
    ):
        violations.append(
            Violation(path, f"{own_module} must not import {top_level_name} (HTTP framework)")
        )
    library = _matching_library(name)
    if library is None:
        return violations
    owners = EXTERNAL_LIBRARY_OWNERS[library]
    if own_module not in owners.modules and path not in owners.files:
        violations.append(
            Violation(
                path,
                f"{own_module} must not import {library} "
                f"(external access is limited to {owners.describe() or 'no module'})",
            )
        )
    return violations


def _matching_library(name: str) -> str | None:
    """`name`(ドット名)に、最も長く一致する `EXTERNAL_LIBRARY_OWNERS` のキー。"""
    matches = [
        library
        for library in EXTERNAL_LIBRARY_OWNERS
        if name == library or name.startswith(f"{library}.")
    ]
    return max(matches, key=len, default=None)


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
