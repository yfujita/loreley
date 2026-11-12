"""依存ルールのテスト(完了条件 1)。

実際のソースツリー全体を検査するテストと、検査器自体が違反を検出できることを
合成ソースで確かめるテスト(まだ存在しない層に対しても、ルールが効くことの確認)に分かれる。
"""

import ast
from pathlib import Path

import pytest

from tests.architecture.dependency_rules import ALLOWED, find_cycles, find_violations, module_of

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "loreley_indexer"


def load_package_sources() -> dict[str, str]:
    return {
        path.relative_to(PACKAGE_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in PACKAGE_ROOT.rglob("*.py")
    }


# --- 実際のソースツリー ---


def test_package_sources_are_found() -> None:
    sources = load_package_sources()
    assert "config.py" in sources
    assert "common/errors.py" in sources


def test_actual_sources_follow_the_dependency_rules() -> None:
    violations = find_violations(load_package_sources())
    assert [str(v) for v in violations] == []


def test_actual_sources_have_no_import_cycles_between_modules() -> None:
    assert find_cycles(load_package_sources()) == []


def test_api_imports_only_the_facades_of_the_features_and_common() -> None:
    """R1・R2・R4: api は infrastructure を直接 import しない(P5)。使うのは機能の入口だけ。"""
    api_sources = {
        path: source for path, source in load_package_sources().items() if path.startswith("api/")
    }
    assert {"api/routes.py", "api/errors.py", "api/schemas.py", "api/app.py"} <= set(api_sources)

    imported_modules = {
        name
        for source in api_sources.values()
        for node in ast.walk(ast.parse(source))
        for name in _imported_module_names(node)
        if name.startswith("loreley_indexer")
    }

    assert not [name for name in imported_modules if "infrastructure" in name]
    assert not [name for name in imported_modules if name.startswith("loreley_indexer.config")]
    assert {name.split(".")[1] for name in imported_modules if "." in name} <= {
        "api",
        "common",
        "crawl_runs",
        "documents",
    }
    # `crawl_runs`・`documents` の入口(`__init__`)だけを使い、内部のモジュールには触れない。
    assert [name for name in imported_modules if name.count(".") > 2 and "api" not in name] == []


def _imported_module_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        return [node.module]
    return []


def test_common_is_a_leaf_in_the_rules() -> None:
    assert ALLOWED["common"] == frozenset()


def test_config_imports_the_api_only_through_its_entrance() -> None:
    """`crawl_runs` と同様。`ApiConfig` は入口から取り、`api` の内部には触れない。"""
    config_source = load_package_sources()["config.py"]

    api_imports = {
        name
        for node in ast.walk(ast.parse(config_source))
        for name in _imported_module_names(node)
        if name.startswith("loreley_indexer.api")
    }

    assert api_imports == {"loreley_indexer.api"}


def test_no_module_other_than_main_depends_on_config() -> None:
    importers = {module for module, allowed in ALLOWED.items() if "config" in allowed}
    assert importers == {"main"}


# --- 検査器の自己テスト(合成ソース) ---
#
# 制約: 検査は AST の import 文だけを見る。`importlib.import_module(...)` や `__import__(...)`
# などの動的な import、文字列から組み立てたモジュール名は検出できない。


def violations_of(sources: dict[str, str]) -> list[str]:
    return [str(v) for v in find_violations(sources)]


def test_any_module_may_import_common() -> None:
    sources = {
        "common/errors.py": "",
        "api/routes.py": "from loreley_indexer.common.errors import X",
        "infrastructure/opensearch/a.py": "from loreley_indexer.common import errors",
        "documents/extraction/a.py": "from ...common.errors import X",
    }
    assert violations_of(sources) == []


# 許可された経路(正例)。許可表の書き間違いで、必要な依存まで塞がないことの確認。
@pytest.mark.parametrize(
    ("path", "import_statement"),
    [
        ("api/routes.py", "from loreley_indexer.crawl_runs import service"),
        ("api/routes.py", "from loreley_indexer.documents import service"),
        ("documents/indexing.py", "from loreley_indexer.infrastructure.opensearch import Conflict"),
        ("documents/indexing.py", "from loreley_indexer.crawl_runs.lifecycle import admission"),
        ("documents/indexing.py", "from loreley_indexer.documents import extraction"),
        (
            "documents/summarization/worker.py",
            "from loreley_indexer.infrastructure.llm import LlmClient",
        ),
        (
            "documents/summarization/worker.py",
            "from loreley_indexer.infrastructure.opensearch import Conflict",
        ),
        (
            "crawl_runs/deletion/worker.py",
            "from loreley_indexer.infrastructure.opensearch import Conflict",
        ),
        (
            "crawl_runs/lifecycle/records.py",
            "from loreley_indexer.infrastructure.opensearch import Conflict",
        ),
        ("crawl_runs/service.py", "from loreley_indexer.crawl_runs.deletion import worker"),
        ("main.py", "from loreley_indexer.config import Settings"),
        ("main.py", "from loreley_indexer.api import routes"),
        ("main.py", "from loreley_indexer.documents.summarization import worker"),
        ("main.py", "from loreley_indexer.infrastructure.llm import LlmClient"),
        ("config.py", "from loreley_indexer.infrastructure.opensearch import IndexNames"),
        ("config.py", "from loreley_indexer.documents.extraction import ExtractionConfig"),
        ("documents/service.py", "from loreley_indexer.crawl_runs import AdmissionChecker"),
    ],
)
def test_allowed_import_paths_have_no_violations(path: str, import_statement: str) -> None:
    sources = {
        path: import_statement,
        "api/routes.py": "",
        "api/service.py": "",
        "crawl_runs/service.py": "",
        "crawl_runs/deletion/worker.py": "",
        "crawl_runs/lifecycle/admission.py": "",
        "documents/service.py": "",
        "documents/extraction/__init__.py": "",
        "documents/summarization/worker.py": "",
    } | {path: import_statement}
    assert violations_of(sources) == []


def test_common_must_not_import_other_modules() -> None:  # M-16
    sources = {"common/x.py": "from loreley_indexer.infrastructure.opensearch import Conflict"}
    assert violations_of(sources) == [
        "common/x.py: common must not import infrastructure.opensearch "
        "(imports 'infrastructure.opensearch'; allowed: ['common'])"
    ]


def test_api_must_not_import_infrastructure() -> None:  # R1、R2、R4
    sources = {"api/routes.py": "from loreley_indexer.infrastructure.opensearch import Conflict"}
    [violation] = violations_of(sources)
    assert violation.startswith("api/routes.py: api must not import infrastructure.opensearch")


def test_infrastructure_must_not_import_upper_layers() -> None:  # R1
    sources = {
        "infrastructure/opensearch/a.py": "from loreley_indexer.documents import indexing",
        "documents/indexing.py": "",
    }
    [violation] = violations_of(sources)
    assert violation.startswith(
        "infrastructure/opensearch/a.py: infrastructure.opensearch must not import documents"
    )


def test_infrastructure_modules_must_not_import_each_other() -> None:
    sources = {"infrastructure/llm/a.py": "from loreley_indexer.infrastructure.opensearch import x"}
    [violation] = violations_of(sources)
    assert violation.startswith(
        "infrastructure/llm/a.py: infrastructure.llm must not import infrastructure.opensearch"
    )


def test_documents_may_import_crawl_runs_lifecycle() -> None:  # R3
    allowed = {
        "documents/indexing.py": "from loreley_indexer.crawl_runs.lifecycle import admission",
        "crawl_runs/lifecycle/admission.py": "",
    }
    assert violations_of(allowed) == []


def test_documents_must_not_import_crawl_runs_deletion() -> None:  # R3
    sources = {
        "documents/indexing.py": "from loreley_indexer.crawl_runs.deletion import worker",
        "crawl_runs/deletion/worker.py": "",
    }
    [violation] = violations_of(sources)
    assert violation.startswith(
        "documents/indexing.py: documents must not import crawl_runs.deletion"
    )


@pytest.mark.parametrize(
    "path", ["crawl_runs/service.py", "crawl_runs/lifecycle/a.py", "crawl_runs/deletion/a.py"]
)
def test_crawl_runs_modules_must_not_import_documents(path: str) -> None:  # R3(依存は一方向)
    sources = {path: "from loreley_indexer.documents import indexing", "documents/indexing.py": ""}
    [violation] = violations_of(sources)
    assert f"{path}: " in violation
    assert "must not import documents" in violation


def test_lifecycle_must_not_import_deletion() -> None:  # R5
    sources = {
        "crawl_runs/lifecycle/a.py": "from loreley_indexer.crawl_runs.deletion import worker",
        "crawl_runs/deletion/worker.py": "",
    }
    [violation] = violations_of(sources)
    assert violation.startswith(
        "crawl_runs/lifecycle/a.py: crawl_runs.lifecycle must not import crawl_runs.deletion"
    )


def test_deletion_may_import_lifecycle() -> None:  # R5
    sources = {
        "crawl_runs/deletion/worker.py": "from loreley_indexer.crawl_runs import lifecycle",
        "crawl_runs/lifecycle/__init__.py": "",
    }
    assert violations_of(sources) == []


def test_extraction_and_summarization_must_not_call_each_other() -> None:
    sources = {
        "documents/extraction/a.py": "from loreley_indexer.documents.summarization import x",
        "documents/summarization/b.py": "from loreley_indexer.documents import extraction",
    }
    violations = violations_of(sources)
    assert len(violations) == 2
    assert "documents.extraction must not import documents.summarization" in violations[0]
    assert "documents.summarization must not import documents.extraction" in violations[1]


def test_summarization_must_not_call_back_into_documents() -> None:
    sources = {"documents/summarization/a.py": "from loreley_indexer.documents import indexing"}
    [violation] = violations_of(sources)
    assert "documents.summarization must not import documents" in violation


def test_only_summarization_may_use_the_llm_client() -> None:  # M-11、R9
    sources = {
        "documents/summarization/a.py": "from loreley_indexer.infrastructure.llm import LlmClient",
        "documents/indexing.py": "from loreley_indexer.infrastructure.llm import LlmClient",
        "crawl_runs/deletion/a.py": "from loreley_indexer.infrastructure.llm import LlmClient",
    }
    violations = violations_of(sources)
    assert [v.split(":")[0] for v in violations] == [
        "crawl_runs/deletion/a.py",
        "documents/indexing.py",
    ]
    assert "crawl_runs.deletion must not import infrastructure.llm" in violations[0]
    assert "documents must not import infrastructure.llm" in violations[1]


def test_modules_must_not_import_config() -> None:
    sources = {
        "documents/indexing.py": "from loreley_indexer.config import Settings",
        "main.py": "from loreley_indexer.config import Settings",
        "config.py": "",
    }
    [violation] = violations_of(sources)
    assert violation.startswith("documents/indexing.py: documents must not import config")


def test_external_system_libraries_are_limited_to_infrastructure() -> None:  # R2
    sources = {
        "documents/indexing.py": "import opensearchpy",
        "api/routes.py": "from httpx import Client",
        "crawl_runs/lifecycle/a.py": "from opensearchpy.exceptions import NotFoundError",
        "infrastructure/opensearch/a.py": "from opensearchpy import OpenSearch",
        "infrastructure/llm/a.py": "import httpx",
        "infrastructure/opensearch/b.py": "import httpx2",
        "api/schemas.py": "import httpx2",  # テストのクライアントの依存。本番のコードは使わない
        "main.py": "from httpx2 import Client",
    }
    violations = violations_of(sources)
    assert [v.split(":")[0] for v in violations] == [
        "api/routes.py",
        "api/schemas.py",
        "crawl_runs/lifecycle/a.py",
        "documents/indexing.py",
        "main.py",
    ]
    assert "api must not import httpx" in violations[0]
    assert "api must not import httpx2" in violations[1]
    assert "crawl_runs.lifecycle must not import opensearchpy" in violations[2]
    assert "documents must not import opensearchpy" in violations[3]
    assert "main must not import httpx2" in violations[4]


def test_llm_sdks_are_not_allowed_in_the_opensearch_module() -> None:
    sources = {"infrastructure/opensearch/a.py": "import anthropic"}
    [violation] = violations_of(sources)
    assert "infrastructure.opensearch must not import anthropic" in violation


@pytest.mark.parametrize(
    "statement",
    [
        "import opensearchpy.exceptions",  # ドット形式
        "import opensearchpy.exceptions as errors",
        "from opensearchpy.exceptions import NotFoundError",
    ],
)
def test_external_library_import_forms_are_detected(statement: str) -> None:
    [violation] = violations_of({"documents/a.py": statement})
    assert "documents must not import opensearchpy" in violation


@pytest.mark.parametrize(
    "statement",
    [
        "import loreley_indexer.infrastructure.opensearch as os_module",
        "import loreley_indexer.infrastructure.opensearch.results",
        "from loreley_indexer.infrastructure import opensearch",
        "from ..infrastructure.opensearch import Conflict",
    ],
)
def test_internal_import_forms_are_detected(statement: str) -> None:
    sources = {
        "api/routes.py": statement,
        "infrastructure/opensearch/results.py": "",
        "infrastructure/opensearch/__init__.py": "",
    }
    [violation] = violations_of(sources)
    assert "api must not import infrastructure.opensearch" in violation


def test_internal_import_of_a_submodule_in_the_dotted_form_is_detected() -> None:
    sources = {
        "api/routes.py": "import loreley_indexer.documents.indexing as indexing",
        "crawl_runs/lifecycle/a.py": "import loreley_indexer.documents.indexing as indexing",
        "documents/indexing.py": "",
    }
    [violation] = violations_of(sources)
    assert violation.startswith("crawl_runs/lifecycle/a.py: crawl_runs.lifecycle must not import")


@pytest.mark.parametrize(
    "source",
    [
        "def load():\n    from loreley_indexer.infrastructure.opensearch import Conflict\n",
        (
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from loreley_indexer.infrastructure.opensearch import Conflict\n"
        ),
        (
            "try:\n"
            "    from loreley_indexer.infrastructure.opensearch import Conflict\n"
            "except ImportError:\n"
            "    pass\n"
        ),
    ],
)
def test_imports_inside_functions_and_blocks_are_detected(source: str) -> None:
    [violation] = violations_of({"api/routes.py": source})
    assert "api must not import infrastructure.opensearch" in violation


def test_relative_imports_are_resolved() -> None:
    sources = {
        "documents/summarization/a.py": "from ..extraction import x",
        "documents/extraction/x.py": "",
    }
    [violation] = violations_of(sources)
    assert violation.startswith(
        "documents/summarization/a.py: documents.summarization must not import documents.extraction"
    )


def test_unclassified_files_and_imports_are_reported() -> None:
    sources = {
        "utils/helpers.py": "",
        "api/a.py": "from loreley_indexer.utils import helpers",
    }
    assert violations_of(sources) == [
        "api/a.py: imports unclassified module 'utils.helpers'",
        "utils/helpers.py: unclassified file (update dependency rules)",
    ]


def test_import_cycles_between_modules_are_detected() -> None:  # R1
    sources = {
        "documents/indexing.py": "from loreley_indexer.crawl_runs import lifecycle",
        "crawl_runs/lifecycle/a.py": "from loreley_indexer.documents import indexing",
    }
    cycles = find_cycles(sources)
    assert cycles
    assert set(cycles[0]) == {"documents", "crawl_runs.lifecycle"}


def test_empty_layers_pass() -> None:
    assert find_violations({}) == []
    assert find_cycles({}) == []


@pytest.mark.parametrize(
    ("dotted", "expected"),
    [
        ("", "namespace"),
        ("infrastructure", "namespace"),
        ("main", "main"),
        ("crawl_runs", "crawl_runs"),
        ("crawl_runs.lifecycle.records", "crawl_runs.lifecycle"),
        ("crawl_runs.facade", "crawl_runs"),
        ("documents.indexing", "documents"),
        ("documents.extraction.html", "documents.extraction"),
        ("infrastructure.opensearch.results", "infrastructure.opensearch"),
        ("infrastructure.cache", None),
        ("other", None),
    ],
)
def test_module_classification(dotted: str, expected: str | None) -> None:
    assert module_of(dotted) == expected


def test_config_may_import_the_documents_modules_that_hold_config_dataclasses() -> None:
    sources = {
        "config.py": (
            "from loreley_indexer.documents import RegistrationConfig\n"
            "from loreley_indexer.documents.summarization import SummarizationConfig\n"
            "from loreley_indexer.documents.extraction import ExtractionConfig"
        ),
        "documents/__init__.py": "",
        "documents/summarization/__init__.py": "",
        "documents/extraction/__init__.py": "",
    }
    assert violations_of(sources) == []


def test_config_may_import_crawl_runs_for_its_config_dataclass() -> None:
    sources = {
        "config.py": "from loreley_indexer.crawl_runs import LifecycleConfig",
        "crawl_runs/__init__.py": "",
    }
    assert violations_of(sources) == []


@pytest.mark.parametrize("submodule", ["lifecycle", "deletion"])
def test_config_must_import_crawl_runs_only_through_its_entrance(submodule: str) -> None:
    sources = {
        "config.py": f"from loreley_indexer.crawl_runs.{submodule} import x",
        f"crawl_runs/{submodule}/__init__.py": "",
    }
    [violation] = violations_of(sources)
    assert violation.startswith(f"config.py: config must not import crawl_runs.{submodule}")
