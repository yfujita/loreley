"""依存ルールのテスト(完了条件 1)。

実際のソースツリー全体を検査するテストと、検査器自体が違反を検出できることを
合成ソースで確かめるテスト(まだ実装がない層に対しても、ルールが効くことの確認)に分かれる。
"""

import ast
import re
from pathlib import Path

import pytest

from tests.architecture.dependency_rules import ALLOWED, find_cycles, find_violations, module_of

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "loreley_crawler"

# module-structure 3章のディレクトリ構成(パッケージルートからの相対)。実装が空でも存在する。
PLANNED_PACKAGES = [
    "common",
    "api",
    "scheduler",
    "sources",
    "jobs",
    "jobs/records",
    "jobs/locks",
    "crawl",
    "source_delete",
    "documents",
    "connectors",
    "connectors/interface",
    "connectors/filesystem",
    "infrastructure",
    "infrastructure/opensearch",
    "infrastructure/indexer_client",
]

APPLICATION_FEATURES = {"jobs", "sources", "crawl", "source_delete", "documents", "connectors"}


def load_package_sources() -> dict[str, str]:
    return {
        path.relative_to(PACKAGE_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in PACKAGE_ROOT.rglob("*.py")
    }


def violations_of(sources: dict[str, str]) -> list[str]:
    return [str(v) for v in find_violations(sources)]


# --- 実際のソースツリー ---


def test_package_sources_are_found() -> None:
    sources = load_package_sources()
    assert "config.py" in sources
    assert "common/retry.py" in sources


@pytest.mark.parametrize("package", PLANNED_PACKAGES)
def test_every_planned_directory_exists_as_a_classified_package(package: str) -> None:
    assert (PACKAGE_ROOT / package / "__init__.py").is_file()
    assert module_of(package.replace("/", ".")) is not None


def test_every_classifiable_module_has_a_row_in_the_allowed_table() -> None:
    modules = {module_of(package.replace("/", ".")) for package in PLANNED_PACKAGES}
    modules |= {module_of(name) for name in ("main", "config", "")}
    assert modules <= set(ALLOWED)


def test_actual_sources_follow_the_dependency_rules() -> None:
    assert violations_of(load_package_sources()) == []


def test_actual_sources_have_no_import_cycles_between_modules() -> None:
    assert find_cycles(load_package_sources()) == []


def test_the_checker_fails_on_a_violating_file_added_to_the_actual_tree() -> None:
    """検査器が実際のツリーに対しても働くこと(現状で成功するだけのテストにしない)。"""
    sources = load_package_sources()
    assert violations_of(sources) == []

    sources["api/fake_handler.py"] = "from loreley_crawler.crawl import runner\n"
    sources["common/fake_helper.py"] = "import loreley_crawler.config\n"
    sources["connectors/filesystem/fake.py"] = "import opensearchpy\n"

    violations = violations_of(sources)
    assert [v.split(":")[0] for v in violations] == [
        "api/fake_handler.py",
        "common/fake_helper.py",
        "connectors/filesystem/fake.py",
    ]
    # `config` は各モジュールを import する(P8)ので、`common` からの違反は循環にもなる。
    # 循環の検査は、`common` に違反を足さない木で行う(違反の 2 件とは別に確かめる)。
    del sources["common/fake_helper.py"]
    assert find_cycles(sources) == []


# --- ルールの表そのもの ---


def test_common_is_a_leaf_in_the_rules() -> None:  # R10
    assert ALLOWED["common"] == frozenset()


def test_application_features_depend_on_each_other_only_along_the_nine_edges() -> None:  # R3
    edges = {
        (feature, target.split(".")[0])
        for feature in APPLICATION_FEATURES
        for target in ALLOWED[feature]
        if target.split(".")[0] in APPLICATION_FEATURES and target.split(".")[0] != feature
    }
    assert edges == {
        ("jobs", "sources"),
        ("crawl", "jobs"),
        ("crawl", "sources"),
        ("crawl", "documents"),
        ("crawl", "connectors"),
        ("source_delete", "jobs"),
        ("source_delete", "sources"),
        ("sources", "connectors"),
        ("documents", "connectors"),
    }


def test_the_allowed_table_is_exactly_the_reviewed_one() -> None:
    """許可表の全ての辺を固定する。辺を足す・減らす変更は、このテストの更新(= 設計の確認)を伴う。

    infrastructure と内部モジュールの辺を含む(R1〜R6・R10)。行ごとの根拠は `dependency_rules.py`。
    """
    assert {module: set(allowed) for module, allowed in ALLOWED.items()} == {
        "api": {"jobs", "sources"},
        "scheduler": {"jobs", "sources"},
        "jobs": {"jobs.records", "jobs.locks", "sources", "infrastructure.opensearch"},
        "jobs.records": {"infrastructure.opensearch"},
        "jobs.locks": {"infrastructure.opensearch"},
        "sources": {"connectors", "connectors.interface", "infrastructure.opensearch"},
        "crawl": {
            "jobs",
            "sources",
            "documents",
            "connectors",
            "connectors.interface",
            "infrastructure.indexer_client",
        },
        "source_delete": {"jobs", "sources", "infrastructure.indexer_client"},
        "documents": {"connectors.interface"},
        "connectors": {"connectors.filesystem", "connectors.interface"},
        "connectors.filesystem": {"connectors.interface"},
        "connectors.interface": set(),
        "infrastructure.opensearch": set(),
        "infrastructure.indexer_client": set(),
        "main": {
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
        },
        "config": {
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
        },
        "namespace": set(),
        "common": set(),
    }


@pytest.mark.parametrize("executor", ["crawl", "source_delete"])
@pytest.mark.parametrize("internal", ["jobs.records", "jobs.locks"])
def test_job_executors_reach_jobs_only_through_its_entrance(executor: str, internal: str) -> None:
    """`crawl`・`source_delete` は、`jobs` の内部(`records/`・`locks/`)を直接 import しない。

    記録の読み書き・ロックは `jobs` の入口(公開する操作)を通す(R3・R6・R7)。
    """
    assert internal not in ALLOWED[executor]
    path = f"{executor}/a.py"
    module_path = internal.replace(".", "/")
    sources = {path: f"from loreley_crawler.{internal} import x", f"{module_path}/b.py": ""}

    [violation] = violations_of(sources)

    assert violation.startswith(f"{path}: {executor} must not import {internal}")


def test_only_main_depends_on_config() -> None:
    importers = {module for module, allowed in ALLOWED.items() if "config" in allowed}
    assert importers == {"main"}


def test_nothing_depends_on_main() -> None:
    assert not [module for module, allowed in ALLOWED.items() if "main" in allowed]


def test_connectors_use_no_infrastructure_module_in_the_mvp() -> None:  # R2、R5
    for module in ("connectors", "connectors.filesystem", "connectors.interface"):
        assert not [name for name in ALLOWED[module] if name.startswith("infrastructure")]


def test_config_imports_other_modules_only_through_their_entrances() -> None:
    """`config.py` が内部のモジュール(`jobs.records` など)に触れる設計にしない。"""
    internal = {"jobs.records", "jobs.locks", "connectors.filesystem", "connectors.interface"}
    assert not ALLOWED["config"] & internal


# --- 検査器の自己テスト(合成ソース) ---
#
# 制約: 検査は AST の import 文だけを見る。`importlib.import_module(...)` や `__import__(...)`
# などの動的な import、文字列から組み立てたモジュール名は検出できない。


def test_any_module_may_import_common() -> None:  # R10
    sources = {
        "common/errors.py": "",
        "api/routes.py": "from loreley_crawler.common.errors import X",
        "infrastructure/opensearch/a.py": "from loreley_crawler.common import errors",
        "connectors/interface/a.py": "from ...common.errors import X",
        "jobs/locks/a.py": "from ...common.retry import run_with_retry",
    }
    assert violations_of(sources) == []


def test_common_must_not_import_other_modules() -> None:  # R10
    sources = {"common/x.py": "from loreley_crawler.infrastructure.opensearch import Repository"}
    assert violations_of(sources) == [
        "common/x.py: common must not import infrastructure.opensearch "
        "(imports 'infrastructure.opensearch'; allowed: ['common'])"
    ]


@pytest.mark.parametrize("target", ["config", "sources", "jobs", "connectors.interface"])
def test_common_must_not_import_any_other_package_of_crawler(target: str) -> None:  # R10
    [violation] = violations_of({"common/x.py": f"import loreley_crawler.{target}"})
    assert violation.startswith(f"common/x.py: common must not import {target}")


# 許可された経路(正例)。許可表の書き間違いで、必要な依存まで塞がないことの確認。
@pytest.mark.parametrize(
    ("path", "import_statement"),
    [
        ("api/routes.py", "from loreley_crawler.jobs import accept_manual_crawl"),
        ("api/routes.py", "from loreley_crawler.sources import SourceRegistry"),
        ("scheduler/runner.py", "from loreley_crawler.jobs import accept_scheduled_crawl"),
        ("scheduler/runner.py", "from loreley_crawler.sources import SourceRegistry"),
        ("jobs/admission.py", "from loreley_crawler.sources import SourceReader"),
        ("jobs/admission.py", "from loreley_crawler.jobs.records import JobRecord"),
        ("jobs/admission.py", "from loreley_crawler.jobs.locks import LockStore"),
        ("jobs/admission.py", "from loreley_crawler.infrastructure.opensearch import Repository"),
        (
            "jobs/records/jobs.py",
            "from loreley_crawler.infrastructure.opensearch import Repository",
        ),
        ("jobs/locks/heartbeat.py", "from loreley_crawler.infrastructure.opensearch import Result"),
        ("sources/registry.py", "from loreley_crawler.connectors import ConnectorRegistry"),
        ("sources/registry.py", "from loreley_crawler.connectors.interface import ConnectorError"),
        ("sources/registry.py", "from loreley_crawler.infrastructure.opensearch import Repository"),
        ("crawl/runner.py", "from loreley_crawler.jobs import JobContext"),
        ("crawl/runner.py", "from loreley_crawler.sources import SourceReader"),
        ("crawl/runner.py", "from loreley_crawler.documents import wrap_enumeration"),
        ("crawl/runner.py", "from loreley_crawler.connectors import ConnectorRegistry"),
        ("crawl/runner.py", "from loreley_crawler.connectors.interface import Connector"),
        ("crawl/runner.py", "from loreley_crawler.infrastructure.indexer_client import Client"),
        ("source_delete/runner.py", "from loreley_crawler.jobs import JobContext"),
        ("source_delete/runner.py", "from loreley_crawler.sources import SourceRegistry"),
        ("source_delete/runner.py", "import loreley_crawler.infrastructure.indexer_client"),
        ("documents/enumeration.py", "from loreley_crawler.connectors.interface import Connector"),
        ("connectors/registry.py", "from loreley_crawler.connectors.filesystem import FsType"),
        ("connectors/registry.py", "from loreley_crawler.connectors.interface import Connector"),
        ("connectors/filesystem/a.py", "from loreley_crawler.connectors.interface import X"),
        ("connectors/filesystem/a.py", "from ..interface import X"),
        ("main.py", "from loreley_crawler.config import Settings"),
        ("main.py", "from loreley_crawler.api import create_app"),
        ("main.py", "from loreley_crawler.crawl import CrawlRunner"),
        ("main.py", "from loreley_crawler.source_delete import SourceDeleteRunner"),
        ("main.py", "from loreley_crawler.infrastructure.opensearch import connect"),
        ("config.py", "from loreley_crawler.jobs import JobsConfig"),
        ("config.py", "from loreley_crawler.infrastructure.indexer_client import ClientConfig"),
    ],
)
def test_allowed_import_paths_have_no_violations(path: str, import_statement: str) -> None:
    assert violations_of({path: import_statement}) == []


# --- R1: 層(上から下へだけ。循環させない) ---


@pytest.mark.parametrize(
    ("path", "upper_module"),
    [
        ("infrastructure/opensearch/a.py", "jobs"),
        ("infrastructure/opensearch/a.py", "sources"),
        ("infrastructure/indexer_client/a.py", "crawl"),
        ("infrastructure/indexer_client/a.py", "source_delete"),
        ("infrastructure/opensearch/a.py", "api"),
        ("infrastructure/indexer_client/a.py", "scheduler"),
        ("infrastructure/opensearch/a.py", "connectors"),
    ],
)
def test_infrastructure_must_not_import_upper_layers(path: str, upper_module: str) -> None:
    [violation] = violations_of({path: f"from loreley_crawler.{upper_module} import x"})
    assert f"must not import {upper_module}" in violation


@pytest.mark.parametrize("entry_layer", ["api", "scheduler"])
@pytest.mark.parametrize(
    "path",
    [
        "jobs/a.py",
        "jobs/records/a.py",
        "jobs/locks/a.py",
        "sources/a.py",
        "crawl/a.py",
        "source_delete/a.py",
        "documents/a.py",
        "connectors/a.py",
        "connectors/interface/a.py",
        "infrastructure/opensearch/a.py",
    ],
)
def test_nothing_below_the_entry_layer_imports_the_entry_layer(path: str, entry_layer: str) -> None:
    [violation] = violations_of({path: f"from loreley_crawler.{entry_layer} import x"})
    assert f"must not import {entry_layer}" in violation


def test_api_and_scheduler_must_not_import_each_other() -> None:
    sources = {
        "api/a.py": "from loreley_crawler.scheduler import x",
        "scheduler/a.py": "from loreley_crawler import api",
    }
    violations = violations_of(sources)
    assert "api must not import scheduler" in violations[0]
    assert "scheduler must not import api" in violations[1]


def test_import_cycles_between_modules_are_detected() -> None:
    sources = {
        "sources/a.py": "from loreley_crawler.jobs import x",
        "jobs/a.py": "from loreley_crawler.sources import x",
    }
    cycles = find_cycles(sources)
    assert cycles
    assert set(cycles[0]) == {"jobs", "sources"}


def test_the_import_that_closes_a_cycle_is_also_a_violation() -> None:
    sources = {
        "sources/a.py": "from loreley_crawler.jobs import x",
        "jobs/a.py": "from loreley_crawler.sources import x",
    }
    [violation] = violations_of(sources)
    assert violation.startswith("sources/a.py: sources must not import jobs")


# --- R2: 外部システムへのアクセス ---


def test_external_system_libraries_are_limited_to_infrastructure() -> None:
    sources = {
        "jobs/records/a.py": "import opensearchpy",
        "api/routes.py": "from urllib3 import PoolManager",
        "crawl/a.py": "from opensearchpy.exceptions import NotFoundError",
        "connectors/filesystem/a.py": "import requests",
        "infrastructure/opensearch/a.py": "from opensearchpy import OpenSearch",
        "infrastructure/indexer_client/a.py": "import urllib3",
        "main.py": "from httpx2 import Client",
    }
    violations = violations_of(sources)
    assert [v.split(":")[0] for v in violations] == [
        "api/routes.py",
        "connectors/filesystem/a.py",
        "crawl/a.py",
        "jobs/records/a.py",
        "main.py",
    ]
    assert "api must not import urllib3" in violations[0]
    assert "connectors.filesystem must not import requests" in violations[1]
    assert "crawl must not import opensearchpy" in violations[2]
    assert "jobs.records must not import opensearchpy" in violations[3]
    assert "main must not import httpx2" in violations[4]


def test_the_selected_http_client_urllib3_is_limited_to_indexer_client() -> None:  # CM-U-2
    """`opensearch` は opensearch-py だけで足りるので、urllib3 を直接 import しない。"""
    [violation] = violations_of({"infrastructure/opensearch/a.py": "import urllib3"})
    assert "infrastructure.opensearch must not import urllib3" in violation
    assert violations_of({"infrastructure/indexer_client/a.py": "import urllib3"}) == []


@pytest.mark.parametrize("library", ["httpx", "httpx2", "requests", "aiohttp"])
@pytest.mark.parametrize(
    "path", ["infrastructure/indexer_client/a.py", "infrastructure/opensearch/a.py", "api/a.py"]
)
def test_http_clients_that_were_not_selected_are_not_imported_anywhere(
    path: str, library: str
) -> None:
    [violation] = violations_of({path: f"import {library}"})
    assert f"must not import {library}" in violation


def test_indexer_client_must_not_use_the_opensearch_client_library() -> None:
    [violation] = violations_of({"infrastructure/indexer_client/a.py": "import opensearchpy"})
    assert "infrastructure.indexer_client must not import opensearchpy" in violation


@pytest.mark.parametrize(
    "statement",
    [
        "import opensearchpy.exceptions",
        "import opensearchpy.exceptions as errors",
        "from opensearchpy.exceptions import NotFoundError",
    ],
)
def test_external_library_import_forms_are_detected(statement: str) -> None:
    [violation] = violations_of({"documents/a.py": statement})
    assert "documents must not import opensearchpy" in violation


# --- R3: アプリケーション機能どうし ---


@pytest.mark.parametrize("runner", ["crawl", "source_delete"])
@pytest.mark.parametrize(
    "path", ["jobs/runner.py", "jobs/admission.py", "jobs/records/a.py", "jobs/locks/a.py"]
)
def test_jobs_must_not_import_the_job_executors(path: str, runner: str) -> None:
    """実行対象は main が Job Runner に注入する。jobs が import すると循環する。"""
    [violation] = violations_of({path: f"from loreley_crawler.{runner} import run"})
    assert f"must not import {runner}" in violation


def test_the_actual_job_runner_files_do_not_import_the_job_executors() -> None:
    """Job Runner・受付・`JobContext` など `jobs` 直下の実ファイルが、`crawl`・`source_delete` を
    import しない(R3。実行対象は `main.py` が注入する)。実ファイルに import を足すと違反になる。
    """
    sources = load_package_sources()
    entrance_files = {
        path: source
        for path, source in sources.items()
        if path.startswith("jobs/") and path.count("/") == 1
    }
    assert {"jobs/runner.py", "jobs/admission.py", "jobs/context.py"} <= set(entrance_files)
    assert violations_of(entrance_files) == []

    for executor in ("crawl", "source_delete"):
        mutated = {
            **entrance_files,
            "jobs/runner.py": entrance_files["jobs/runner.py"]
            + f"\nfrom loreley_crawler.{executor} import run\n",
        }

        [violation] = violations_of(mutated)

        assert violation.startswith(f"jobs/runner.py: jobs must not import {executor}")


@pytest.mark.parametrize(
    ("path", "forbidden"),
    [
        ("documents/a.py", "sources"),
        ("documents/a.py", "jobs"),
        ("documents/a.py", "crawl"),
        ("documents/a.py", "connectors"),  # 直下(レジストリ)は不可。interface だけ
        ("documents/a.py", "connectors.filesystem"),
        ("documents/a.py", "infrastructure.opensearch"),
        ("sources/a.py", "documents"),
        ("sources/a.py", "jobs"),
        ("sources/a.py", "crawl"),
        ("sources/a.py", "connectors.filesystem"),
        ("jobs/a.py", "documents"),
        ("jobs/a.py", "connectors"),
        ("jobs/a.py", "infrastructure.indexer_client"),
        ("crawl/a.py", "source_delete"),
        ("crawl/a.py", "infrastructure.opensearch"),
        ("crawl/a.py", "jobs.records"),
        ("crawl/a.py", "connectors.filesystem"),
        ("source_delete/a.py", "crawl"),
        ("source_delete/a.py", "documents"),
        ("source_delete/a.py", "connectors"),
        ("source_delete/a.py", "infrastructure.opensearch"),
    ],
)
def test_application_features_must_not_import_outside_their_allowed_dependencies(
    path: str, forbidden: str
) -> None:
    [violation] = violations_of({path: f"import loreley_crawler.{forbidden}"})
    assert f"must not import {forbidden}" in violation


def test_connectors_must_not_import_other_application_features() -> None:  # R3、R5(葉)
    sources = {
        f"connectors/{name}.py": f"from loreley_crawler.{feature} import x"
        for name, feature in [
            ("a", "sources"),
            ("b", "jobs"),
            ("c", "crawl"),
            ("d", "source_delete"),
            ("e", "documents"),
        ]
    }
    assert len(violations_of(sources)) == 5


# --- R4: api・scheduler は業務判断をしない ---


@pytest.mark.parametrize("path", ["api/routes.py", "scheduler/runner.py"])
@pytest.mark.parametrize(
    "forbidden",
    [
        "crawl",
        "source_delete",
        "connectors",
        "connectors.interface",
        "connectors.filesystem",
        "documents",
        "jobs.records",
        "jobs.locks",
        "infrastructure.opensearch",
        "infrastructure.indexer_client",
    ],
)
def test_api_and_scheduler_must_not_import_the_executors_connectors_or_infrastructure(
    path: str, forbidden: str
) -> None:
    [violation] = violations_of({path: f"from loreley_crawler.{forbidden} import x"})
    assert f"must not import {forbidden}" in violation


# --- R5: connectors の内部と infrastructure どうし ---


def test_infrastructure_modules_must_not_import_each_other() -> None:
    sources = {
        "infrastructure/indexer_client/a.py": "import loreley_crawler.infrastructure.opensearch",
        "infrastructure/opensearch/a.py": "import loreley_crawler.infrastructure.indexer_client",
    }
    violations = violations_of(sources)
    assert (
        "infrastructure.indexer_client must not import infrastructure.opensearch" in violations[0]
    )
    assert (
        "infrastructure.opensearch must not import infrastructure.indexer_client" in violations[1]
    )


@pytest.mark.parametrize("path", ["connectors/a.py", "connectors/filesystem/a.py"])
@pytest.mark.parametrize("infrastructure", ["opensearch", "indexer_client"])
def test_connectors_must_not_import_the_store_or_indexer_clients(
    path: str, infrastructure: str
) -> None:
    [violation] = violations_of(
        {path: f"from loreley_crawler.infrastructure.{infrastructure} import x"}
    )
    assert f"must not import infrastructure.{infrastructure}" in violation


def test_connectors_registry_may_import_filesystem_and_interface() -> None:
    sources = {
        "connectors/registry.py": (
            "from loreley_crawler.connectors.filesystem import FileSystemConnectorType\n"
            "from loreley_crawler.connectors import interface\n"
        ),
        "connectors/filesystem/__init__.py": "",
        "connectors/interface/__init__.py": "",
    }
    assert violations_of(sources) == []


def test_connectors_internals_depend_in_one_direction_only() -> None:
    sources = {
        "connectors/interface/a.py": "from loreley_crawler.connectors.filesystem import x",
        "connectors/filesystem/a.py": "from loreley_crawler.connectors import registry",
        "connectors/filesystem/b.py": "from ...connectors.registry import x",
        "connectors/registry.py": "",
    }
    violations = violations_of(sources)
    assert len(violations) == 3
    assert "connectors.filesystem must not import connectors (imports" in violations[0]
    assert "connectors.filesystem must not import connectors (imports" in violations[1]
    assert "connectors.interface must not import connectors.filesystem" in violations[2]


def test_connectors_interface_imports_nothing_but_common() -> None:
    sources = {
        "connectors/interface/a.py": (
            "from loreley_crawler.common.errors import CrawlerError\n"
            "from loreley_crawler.connectors.interface import b\n"
        ),
        "connectors/interface/b.py": "",
    }
    assert violations_of(sources) == []


# --- R6: jobs の内部 ---


def test_records_and_locks_must_not_import_each_other() -> None:
    sources = {
        "jobs/records/a.py": "from loreley_crawler.jobs.locks import x",
        "jobs/locks/a.py": "from loreley_crawler.jobs import records",
    }
    violations = violations_of(sources)
    assert violations[0].startswith("jobs/locks/a.py: jobs.locks must not import jobs.records")
    assert violations[1].startswith("jobs/records/a.py: jobs.records must not import jobs.locks")


@pytest.mark.parametrize("path", ["jobs/records/a.py", "jobs/locks/a.py"])
def test_records_and_locks_must_not_import_the_jobs_entrance(path: str) -> None:
    [violation] = violations_of({path: "from loreley_crawler.jobs import accept"})
    assert "must not import jobs (imports" in violation


@pytest.mark.parametrize("path", ["jobs/records/a.py", "jobs/locks/a.py"])
def test_records_and_locks_must_not_import_sources(path: str) -> None:
    [violation] = violations_of({path: "from loreley_crawler.sources import x"})
    assert "must not import sources" in violation


# --- config ---


def test_modules_must_not_import_config() -> None:
    sources = {
        "jobs/a.py": "from loreley_crawler.config import Settings",
        "main.py": "from loreley_crawler.config import Settings",
        "config.py": "",
    }
    [violation] = violations_of(sources)
    assert violation.startswith("jobs/a.py: jobs must not import config")


@pytest.mark.parametrize(
    "statement",
    [
        "from loreley_crawler.jobs.records import x",
        "from loreley_crawler.connectors.filesystem import x",
        "from loreley_crawler.connectors.interface import x",
        "from loreley_crawler.crawl import x\nfrom loreley_crawler.main import y",
    ],
)
def test_config_must_not_import_internal_modules_or_main(statement: str) -> None:
    [violation] = violations_of({"config.py": statement})
    assert violation.startswith("config.py: config must not import")


# --- import の書き方 ---


@pytest.mark.parametrize(
    "statement",
    [
        "import loreley_crawler.infrastructure.opensearch as os_module",
        "import loreley_crawler.infrastructure.opensearch.results",
        "from loreley_crawler.infrastructure import opensearch",
        "from ..infrastructure.opensearch import Repository",
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


@pytest.mark.parametrize(
    "source",
    [
        "def load():\n    from loreley_crawler.crawl import run\n",
        (
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from loreley_crawler.crawl import run\n"
        ),
        "try:\n    from loreley_crawler.crawl import run\nexcept ImportError:\n    pass\n",
    ],
)
def test_imports_inside_functions_and_blocks_are_detected(source: str) -> None:
    [violation] = violations_of({"api/routes.py": source})
    assert "api must not import crawl" in violation


def test_relative_imports_are_resolved() -> None:
    sources = {
        "jobs/locks/a.py": "from ..records import x",
        "jobs/records/x.py": "",
    }
    [violation] = violations_of(sources)
    assert violation.startswith("jobs/locks/a.py: jobs.locks must not import jobs.records")


def test_unclassified_files_and_imports_are_reported() -> None:
    sources = {
        "utils/helpers.py": "",
        "infrastructure/cache/a.py": "",
        "api/a.py": "from loreley_crawler.utils import helpers",
    }
    assert violations_of(sources) == [
        "api/a.py: imports unclassified module 'utils.helpers'",
        "infrastructure/cache/a.py: unclassified file (update dependency rules)",
        "utils/helpers.py: unclassified file (update dependency rules)",
    ]


def test_empty_layers_pass() -> None:
    assert find_violations({}) == []
    assert find_cycles({}) == []


@pytest.mark.parametrize(
    ("dotted", "expected"),
    [
        ("", "namespace"),
        ("infrastructure", "namespace"),
        ("main", "main"),
        ("config", "config"),
        ("common.retry", "common"),
        ("api.routes", "api"),
        ("scheduler", "scheduler"),
        ("sources.registry", "sources"),
        ("jobs", "jobs"),
        ("jobs.admission", "jobs"),
        ("jobs.records", "jobs.records"),
        ("jobs.records.jobs", "jobs.records"),
        ("jobs.locks.heartbeat", "jobs.locks"),
        ("crawl.runner", "crawl"),
        ("source_delete", "source_delete"),
        ("documents.enumeration", "documents"),
        ("connectors", "connectors"),
        ("connectors.registry", "connectors"),
        ("connectors.interface.errors", "connectors.interface"),
        ("connectors.filesystem.scan", "connectors.filesystem"),
        ("infrastructure.opensearch.results", "infrastructure.opensearch"),
        ("infrastructure.indexer_client.client", "infrastructure.indexer_client"),
        ("infrastructure.cache", None),
        # Web Connector は MVP では作らない(CM-U-8)。`connectors/web.py` のような直下のファイルは
        # `connectors` として扱い、`connectors/web/` ディレクトリを置くなら、先に分類とルール
        # (`_SUB_MODULES`・`ALLOWED`)を更新する(今は `connectors` の下位として暫定の分類)。
        ("connectors.web", "connectors"),
        ("other", None),
    ],
)
def test_module_classification(dotted: str, expected: str | None) -> None:
    assert module_of(dotted) == expected


# --- main.py(composition root。P8) ---


def main_imported_modules() -> set[str]:
    """実際の `main.py` が import するパッケージ内のモジュール(`common` を除く)。"""
    tree = ast.parse((PACKAGE_ROOT / "main.py").read_text(encoding="utf-8"))
    names = {
        node.module.removeprefix("loreley_crawler.")
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("loreley_crawler.")
    }
    return {module for name in names if (module := module_of(name)) not in (None, "common")}


def test_main_wires_every_feature_module_and_only_allowed_ones() -> None:
    imported = main_imported_modules()

    assert imported <= ALLOWED["main"]
    # 組み立てる側が、機能のモジュール(`documents` は `crawl` の中で使われる)をすべて使う。
    assert {
        "api",
        "scheduler",
        "sources",
        "jobs",
        "jobs.records",
        "jobs.locks",
        "crawl",
        "source_delete",
        "connectors",
        "infrastructure.opensearch",
        "infrastructure.indexer_client",
        "config",
    } <= imported


def test_no_module_other_than_main_imports_main() -> None:
    importers = [
        path
        for path, source in load_package_sources().items()
        if path != "main.py"
        and re.search(r"loreley_crawler\.main\b|from loreley_crawler import .*\bmain\b", source)
    ]

    assert importers == []
