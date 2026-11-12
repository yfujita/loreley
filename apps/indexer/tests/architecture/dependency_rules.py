"""依存ルール R1〜R9(module 6章)のうち、import で検査できるものの検査器。

ファイルを「モジュール」に分類し、許可した import だけを通す。許可表(ALLOWED)が
ルールの実体で、各行に根拠のルール番号を書く。検査は AST で行い、import 文を実行しない。
関数内・`TYPE_CHECKING` 内・`try` 内の import も検査する。

制約: import 文だけが対象で、動的な import(`importlib.import_module`、`__import__`、
文字列から組み立てたモジュール名)は検出できない。
"""

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

PACKAGE = "loreley_indexer"

# 常にどのモジュールからも import してよい(R1: 共通部品。`common` は葉で、誰にも依存しない)。
COMMON = "common"

# モジュール → import してよいモジュール(自分自身と `common` は常に許可)。
ALLOWED: dict[str, frozenset[str]] = {
    # R4: api は形式の検証と受け渡しだけ。依存先は crawl_runs と documents のみ
    # (infrastructure は直接使わない。R1、R2)。
    "api": frozenset({"crawl_runs", "documents"}),
    # R1: アプリケーション機能 → infrastructure。R5: deletion → lifecycle の一方向。
    "crawl_runs": frozenset(
        {"crawl_runs.lifecycle", "crawl_runs.deletion", "infrastructure.opensearch"}
    ),
    "crawl_runs.lifecycle": frozenset({"infrastructure.opensearch"}),
    "crawl_runs.deletion": frozenset({"crawl_runs.lifecycle", "infrastructure.opensearch"}),
    # R3: 機能どうしの依存は documents → crawl_runs の 1 本だけ
    # (受理条件の照会。lifecycle が持つ。M-6)。
    # R9/M-11: LLM を呼べるのは summarization だけ(documents 直下は llm を import しない)。
    "documents": frozenset(
        {
            "documents.extraction",
            "documents.summarization",
            "crawl_runs",
            "crawl_runs.lifecycle",
            "infrastructure.opensearch",
        }
    ),
    # extraction は他へ依存しない(module 4.3)。summarization とも互いを呼ばない。
    "documents.extraction": frozenset(),
    "documents.summarization": frozenset({"infrastructure.opensearch", "infrastructure.llm"}),
    # R2: 外部システムへのアクセスは infrastructure に限る。infrastructure どうしも依存しない。
    "infrastructure.opensearch": frozenset(),
    "infrastructure.llm": frozenset(),
    # `main.py`(組み立て)と `config.py`(設定の読み込み)。モジュールは config に依存しない。
    "main": frozenset(
        {
            "config",
            "api",
            "crawl_runs",
            "crawl_runs.lifecycle",
            "crawl_runs.deletion",
            "documents",
            "documents.extraction",
            "documents.summarization",
            "infrastructure.opensearch",
            "infrastructure.llm",
        }
    ),
    # config.py は、値を各モジュールの設定 dataclass に詰めて main に渡す(module 3章)ため、
    # その dataclass を持つモジュールを import する。どのモジュールも config に依存しないので、
    # config からの依存が循環を作らない(extraction は P2a、documents・summarization は P2b、
    # crawl_runs の LifecycleConfig は P3、api の ApiConfig は P5 で追加)。
    "config": frozenset(
        {
            "api",
            "crawl_runs",
            "documents",
            "documents.extraction",
            "documents.summarization",
            "infrastructure.opensearch",
            "infrastructure.llm",
        }
    ),
    # 名前空間だけのパッケージ(`__init__.py`)。何も import しない。
    "namespace": frozenset(),
    # M-16: common は葉。
    COMMON: frozenset(),
}

# R2: 外部システムに接続するライブラリは、infrastructure の該当モジュールだけが import する。
EXTERNAL_LIBRARY_OWNERS: dict[str, frozenset[str]] = {
    "opensearchpy": frozenset({"infrastructure.opensearch"}),
    "httpx": frozenset({"infrastructure.opensearch", "infrastructure.llm"}),
    "httpx2": frozenset({"infrastructure.opensearch", "infrastructure.llm"}),
    "requests": frozenset({"infrastructure.opensearch", "infrastructure.llm"}),
    "urllib3": frozenset({"infrastructure.opensearch", "infrastructure.llm"}),
    "aiohttp": frozenset({"infrastructure.opensearch", "infrastructure.llm"}),
    "anthropic": frozenset({"infrastructure.llm"}),
    "openai": frozenset({"infrastructure.llm"}),
}


@dataclass(frozen=True)
class Violation:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def module_of(dotted: str) -> str | None:
    """パッケージからの相対のドット名(例: `crawl_runs.lifecycle.records`)を、モジュール名にする。

    分類できなければ None(未知のディレクトリ・ファイルは、ルールの更新を促すため違反にする)。
    """
    parts = dotted.split(".") if dotted else []
    if not parts:
        return "namespace"
    top = parts[0]
    if top in {"main", "config", "api", COMMON}:
        return top
    if top == "infrastructure":
        if len(parts) == 1:
            return "namespace"
        return f"infrastructure.{parts[1]}" if parts[1] in {"opensearch", "llm"} else None
    sub_modules = {
        "crawl_runs": {"lifecycle", "deletion"},
        "documents": {"extraction", "summarization"},
    }
    if top in sub_modules:
        if len(parts) > 1 and parts[1] in sub_modules[top]:
            return f"{top}.{parts[1]}"
        return top
    return None


def dotted_name_of_file(relative_path: str) -> str:
    """`crawl_runs/lifecycle/records.py` → `crawl_runs.lifecycle.records`。

    `__init__.py` はパッケージ名になる。
    """
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
