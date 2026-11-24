"""依存ルールのテスト(D 6章 R1〜R6・R12)。

実際のソースツリー全体を検査するテストと、検査器自体が違反を検出できることを
合成ソースで確かめるテスト(正例・負例。ルールが空振りしていないことの確認)に分かれる。
"""

from pathlib import Path

import pytest

from tests.architecture.dependency_rules import (
    ADMIN_SUBMODULES,
    COMMON,
    EXTERNAL_LIBRARY_OWNERS,
    FEATURE_PACKAGES,
    INFRASTRUCTURE_MODULES,
    build_allowed,
    dotted_name_of_file,
    find_cycles,
    find_violations,
    module_of,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "loreley_api"


def load_package_sources() -> dict[str, str]:
    return {
        path.relative_to(PACKAGE_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in PACKAGE_ROOT.rglob("*.py")
    }


def violations_of(
    sources: dict[str, str], feature_packages: frozenset[str] = FEATURE_PACKAGES
) -> list[str]:
    return [str(v) for v in find_violations(sources, feature_packages)]


# --- 実際のソースツリー ---


def test_package_sources_are_found() -> None:
    sources = load_package_sources()
    assert {"main.py", "config.py", "server/app.py", "health/router.py", "admin/app.py"} <= set(
        sources
    )
    assert "common/http/middleware.py" in sources
    assert "admin/routers/request_input.py" in sources
    assert "infrastructure/opensearch/config.py" in sources


def test_actual_sources_follow_the_dependency_rules() -> None:
    violations = find_violations(load_package_sources())
    assert [str(v) for v in violations] == []


def test_actual_sources_have_no_import_cycles_between_modules() -> None:
    assert find_cycles(load_package_sources()) == []


def test_every_actual_file_is_classified() -> None:
    """未分類のファイルは違反になる。分類漏れがあれば、ここで名前が分かる。"""
    unclassified = [
        path for path in load_package_sources() if module_of(dotted_name_of_file(path)) is None
    ]
    assert unclassified == []


def test_health_and_admin_are_feature_packages() -> None:
    assert {"health", "admin"} <= FEATURE_PACKAGES


def test_server_does_not_import_a_feature_package() -> None:
    """プランの受け入れ基準: `server` は `health` を import しない(R3)。"""
    server_sources = {
        path: source
        for path, source in load_package_sources().items()
        if path.startswith("server/")
    }
    assert "server/app.py" in server_sources
    assert violations_of(server_sources) == []
    assert build_allowed()["server"] == frozenset()


def test_common_is_a_leaf_in_the_rules() -> None:
    assert build_allowed()[COMMON] == frozenset()


def test_no_module_other_than_main_depends_on_config() -> None:
    importers = {module for module, allowed in build_allowed().items() if "config" in allowed}
    assert importers == {"main"}


def test_only_main_and_config_may_import_the_feature_packages() -> None:
    """`config` は、設定型を持つ `admin` の入口だけを import できる(`health` は不可)。"""
    importers = {
        module
        for module, allowed in build_allowed().items()
        if allowed & FEATURE_PACKAGES  # 機能パッケージを import できるモジュール
    }
    assert importers == {"main", "config"}
    assert build_allowed()["config"] & FEATURE_PACKAGES == {"admin"}


def test_the_allowed_table_is_fixed() -> None:
    """許可表の全辺。辺を足す・減らすときは、この期待値を意図して更新する(R1〜R6・R12)。"""
    infrastructure = set(INFRASTRUCTURE_MODULES)
    expected = {
        "main": {"config", "server", "health", "admin", *infrastructure},
        "config": {"admin", *infrastructure},
        "server": set(),
        "health": set(),
        "namespace": set(),
        "common": set(),
        "admin": {
            "admin.routers",
            "admin.services",
            "admin.schemas",
            "admin.base",
            *infrastructure,
        },
        "admin.routers": {"admin.services", "admin.schemas", "admin.base"},
        "admin.services": {
            "admin.derivation",
            "admin.crawler_mapping",
            "admin.failures",
            "admin.schemas",
            "admin.base",
            *infrastructure,
        },
        "admin.crawler_mapping": {"admin.base", "infrastructure.crawler_client"},
        "admin.failures": {"admin.base"},
        "admin.derivation": {"admin.base"},
        "admin.schemas": {"admin.base"},
        "admin.base": set(),
        "infrastructure.opensearch": set(),
        "infrastructure.crawler_client": set(),
        "infrastructure.probes": set(),
    }
    assert {module: set(allowed) for module, allowed in build_allowed().items()} == expected


# --- 検査器の自己テスト(合成ソース) ---
#
# 制約: 検査は AST の import 文だけを見る。`importlib.import_module(...)` や `__import__(...)`
# などの動的な import、文字列から組み立てたモジュール名は検出できない。

# 合成の 2 つ目の機能パッケージ。ルールが `health` 固有の書き方でないことの確認。
TWO_FEATURES = frozenset({"health", "dummy"})


def test_any_module_may_import_common() -> None:
    sources = {
        "common/http/errors.py": "",
        "server/app.py": "from loreley_api.common.http import install_common_http",
        "health/router.py": "from loreley_api.common.http.errors import ApiError",
        "config.py": "from loreley_api.common import http",
        "dummy/router.py": "from ..common.http import errors",
    }
    assert violations_of(sources, TWO_FEATURES) == []


# 許可された経路(正例)。許可表の書き間違いで、必要な依存まで塞がないことの確認。
@pytest.mark.parametrize(
    ("path", "import_statement"),
    [
        ("main.py", "from loreley_api.config import load_settings"),
        ("main.py", "from loreley_api.server import create_app"),
        ("main.py", "from loreley_api.health import create_health_router"),
        ("main.py", "from loreley_api.dummy import create_dummy_router"),
        ("main.py", "from loreley_api.common.logging_setup import configure_logging"),
        ("server/app.py", "from loreley_api.server import app"),
        ("health/router.py", "from loreley_api.health import router"),
        ("dummy/router.py", "from loreley_api.dummy import schemas"),
    ],
)
def test_allowed_import_paths_have_no_violations(path: str, import_statement: str) -> None:
    sources = {
        "health/__init__.py": "",
        "dummy/__init__.py": "",
        "dummy/schemas.py": "",
        "server/__init__.py": "",
        "server/app.py": "",
        "health/router.py": "",
        "dummy/router.py": "",
        "common/logging_setup.py": "",
        "config.py": "",
    } | {path: import_statement}
    assert violations_of(sources, TWO_FEATURES) == []


def test_fastapi_and_starlette_are_not_restricted() -> None:
    """HTTP の枠組み(fastapi・starlette)は、どのモジュールも使ってよい。"""
    sources = {
        "common/http/middleware.py": "from starlette.requests import Request",
        "server/app.py": "from fastapi import FastAPI\nfrom starlette.types import Lifespan",
        "health/router.py": "from fastapi import APIRouter",
    }
    assert violations_of(sources) == []


def test_common_must_not_import_other_modules() -> None:  # R12
    sources = {
        "common/x.py": "from loreley_api.server import create_app",
        "server/__init__.py": "",
    }
    assert violations_of(sources) == [
        "common/x.py: common must not import server (imports 'server'; allowed: ['common'])"
    ]


@pytest.mark.parametrize(
    "importer",
    ["common/x.py", "server/app.py", "health/router.py"],
)
def test_nothing_but_main_may_import_config(importer: str) -> None:
    sources = {importer: "from loreley_api.config import Settings"}
    [violation] = violations_of(sources)
    assert violation.startswith(f"{importer}: ")
    assert "must not import config" in violation


def test_server_must_not_import_a_feature_package() -> None:  # R3
    sources = {
        "server/app.py": "from loreley_api.health import create_health_router",
        "health/__init__.py": "",
    }
    [violation] = violations_of(sources)
    assert violation.startswith("server/app.py: server must not import health")


def test_a_plain_import_statement_is_checked_too() -> None:
    sources = {
        "health/router.py": "import loreley_api.server.app",
        "server/app.py": "",
        "server/__init__.py": "",
    }
    [violation] = violations_of(sources)
    assert violation.startswith("health/router.py: health must not import server")


def test_a_feature_package_must_not_import_server() -> None:  # R1(下の層から上の層へ)
    sources = {
        "health/router.py": "from loreley_api.server import create_app",
        "server/__init__.py": "",
    }
    [violation] = violations_of(sources)
    assert violation.startswith("health/router.py: health must not import server")


def test_feature_packages_must_not_import_each_other() -> None:  # R2
    """2 つ目の機能(合成の `dummy`)を足すと、`health` との相互の import が違反になる。"""
    sources = {
        "health/router.py": "from loreley_api.dummy import create_dummy_router",
        "dummy/router.py": "from loreley_api.health import create_health_router",
        "health/__init__.py": "",
        "dummy/__init__.py": "",
    }
    violations = violations_of(sources, TWO_FEATURES)
    assert len(violations) == 2
    assert "dummy/router.py: dummy must not import health" in violations[0]
    assert "health/router.py: health must not import dummy" in violations[1]


def test_a_feature_package_is_unclassified_until_it_is_added_to_the_rules() -> None:
    """`FEATURE_PACKAGES` に足さない機能のディレクトリは、ルールの更新を促す違反になる。"""
    sources = {"dummy/router.py": ""}
    assert violations_of(sources) == [
        "dummy/router.py: unclassified file (update dependency rules)"
    ]


def test_importing_an_unclassified_module_is_a_violation() -> None:
    sources = {"main.py": "from loreley_api.unknown import x"}
    assert violations_of(sources) == ["main.py: imports unclassified module 'unknown'"]


def test_relative_imports_are_checked() -> None:
    sources = {
        "health/router.py": "from .. import server",
        "server/__init__.py": "",
    }
    [violation] = violations_of(sources)
    assert violation.startswith("health/router.py: health must not import server")


def test_imports_inside_functions_and_type_checking_blocks_are_checked() -> None:
    sources = {
        "health/router.py": (
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from loreley_api.server import SubAppMount\n"
            "def f():\n"
            "    from loreley_api.server import create_app\n"
        ),
        "server/__init__.py": "",
    }
    assert len(violations_of(sources)) == 2


@pytest.mark.parametrize(
    "statement",
    [
        "import requests",
        "import httpx",
        "import httpx2",
        "from httpx2 import Client",
        "import aiohttp",
    ],
)
@pytest.mark.parametrize(
    "path",
    ["main.py", "server/app.py", "health/router.py", "common/x.py", "infrastructure/probes/x.py"],
)
def test_nobody_may_import_a_library_that_has_no_owner(path: str, statement: str) -> None:
    [violation] = violations_of({path: statement})
    assert violation.startswith(f"{path}: ")
    assert "must not import" in violation
    assert "no module" in violation


# R5: 所有者の割り当て(正例と負例)
@pytest.mark.parametrize(
    ("path", "statement"),
    [
        ("infrastructure/opensearch/readonly_client.py", "from opensearchpy import OpenSearch"),
        ("infrastructure/opensearch/x.py", "import opensearchpy"),
        ("infrastructure/crawler_client/http_client.py", "import urllib3"),
        ("infrastructure/crawler_client/http_client.py", "from urllib3 import PoolManager"),
        ("infrastructure/probes/http_probe.py", "from urllib3 import PoolManager, Timeout"),
        ("infrastructure/crawler_client/classification.py", "from urllib3.exceptions import X"),
        ("common/concurrency.py", "import anyio"),
        ("common/concurrency.py", "from anyio import to_thread"),
        # `urllib3.exceptions` の型だけは、OpenSearch の例外の分類の 2 ファイルが import できる。
        ("infrastructure/opensearch/failure.py", "from urllib3.exceptions import HTTPError"),
        ("infrastructure/opensearch/failure.py", "from urllib3 import exceptions"),
        ("infrastructure/opensearch/failure.py", "import urllib3.exceptions"),
        ("infrastructure/opensearch/health_probe.py", "from urllib3.exceptions import HTTPError"),
    ],
)
def test_the_owner_of_an_external_library_may_import_it(path: str, statement: str) -> None:
    assert violations_of({path: statement}) == []


@pytest.mark.parametrize(
    ("path", "statement", "library"),
    [
        ("main.py", "import opensearchpy", "opensearchpy"),
        ("admin/services/x.py", "from opensearchpy import OpenSearch", "opensearchpy"),
        ("infrastructure/crawler_client/x.py", "import opensearchpy", "opensearchpy"),
        ("infrastructure/probes/x.py", "from opensearchpy import OpenSearch", "opensearchpy"),
        ("main.py", "from urllib3 import PoolManager", "urllib3"),
        ("admin/services/x.py", "import urllib3", "urllib3"),
        ("infrastructure/opensearch/x.py", "import urllib3", "urllib3"),
        (
            "infrastructure/opensearch/x.py",
            "from urllib3.exceptions import X",
            "urllib3.exceptions",
        ),
        ("health/router.py", "from urllib3.exceptions import HTTPError", "urllib3.exceptions"),
        # 例外の 2 ファイルでも、`PoolManager` などは import できない。
        ("infrastructure/opensearch/failure.py", "import urllib3", "urllib3"),
        ("infrastructure/opensearch/failure.py", "from urllib3 import PoolManager", "urllib3"),
        ("infrastructure/opensearch/health_probe.py", "from urllib3.util import Retry", "urllib3"),
        # `anyio` は `common/concurrency.py` だけ(`common` 全体ではない)。
        ("common/x.py", "import anyio", "anyio"),
        ("server/app.py", "from anyio import to_thread", "anyio"),
        ("infrastructure/probes/x.py", "import anyio", "anyio"),
        ("main.py", "import anyio", "anyio"),
    ],
)
def test_a_non_owner_must_not_import_an_external_library(
    path: str, statement: str, library: str
) -> None:  # R5
    [violation] = violations_of({path: statement})
    assert violation.startswith(f"{path}: ")
    assert f"must not import {library} " in violation


def test_every_external_library_owner_is_a_known_module_or_file() -> None:
    sources = load_package_sources()
    for library, owners in EXTERNAL_LIBRARY_OWNERS.items():
        assert owners.modules <= set(build_allowed()) | {COMMON}, library
        # 例外のファイルは、実在するか、これから作るファイル(同じモジュールの中)。
        for owner_file in owners.files:
            assert module_of(dotted_name_of_file(owner_file)) is not None, owner_file
    assert "common/concurrency.py" in sources


@pytest.mark.parametrize("library", ["fastapi", "starlette"])
@pytest.mark.parametrize("module", INFRASTRUCTURE_MODULES)
def test_infrastructure_must_not_import_the_http_framework(module: str, library: str) -> None:  # R5
    path = f"{module.replace('.', '/')}/x.py"
    for statement in (f"import {library}", f"from {library}.responses import JSONResponse"):
        [violation] = violations_of({path: statement})
        assert violation == f"{path}: {module} must not import {library} (HTTP framework)"


@pytest.mark.parametrize(
    "statement",
    [
        "from loreley_api.common.http import install_common_http",
        "from loreley_api.common.http.errors import ApiError",
        "import loreley_api.common.http.handlers",
        "from loreley_api.common import http",
        "from ...common import http",
    ],
)
def test_infrastructure_must_not_import_common_http(statement: str) -> None:  # R12
    sources = {
        "infrastructure/opensearch/x.py": statement,
        "common/http/__init__.py": "",
    }
    [violation] = violations_of(sources)
    assert violation.startswith(
        "infrastructure/opensearch/x.py: infrastructure.opensearch must not"
    )
    assert "common.http" in violation


@pytest.mark.parametrize(
    "statement",
    [
        "from loreley_api.common.results import Ok, Failed",
        "from loreley_api.common import results",
        "from loreley_api.common.probe_outcome import ProbeOutcome",
    ],
)
def test_infrastructure_may_import_the_other_common_parts(statement: str) -> None:
    sources = {
        "infrastructure/opensearch/x.py": statement,
        "common/http/__init__.py": "",
        "common/results.py": "",
    }
    assert violations_of(sources) == []


@pytest.mark.parametrize("importer", INFRASTRUCTURE_MODULES)
def test_infrastructure_modules_must_not_import_each_other(importer: str) -> None:  # R6
    for other in INFRASTRUCTURE_MODULES:
        if other == importer:
            continue
        path = f"{importer.replace('.', '/')}/x.py"
        sources = {
            path: f"from loreley_api.{other} import y",
            f"{other.replace('.', '/')}/y.py": "",
        }
        [violation] = violations_of(sources)
        assert violation.startswith(f"{path}: {importer} must not import {other}")


@pytest.mark.parametrize("importer", INFRASTRUCTURE_MODULES)
@pytest.mark.parametrize(
    "statement",
    [
        "from loreley_api.admin.base import codes",
        "from loreley_api.admin import AdminSettings",
        "from loreley_api.server import create_app",
        "from loreley_api.health import create_health_router",
        "from loreley_api.config import ApiConfig",
    ],
)
def test_infrastructure_must_not_import_upper_layers(importer: str, statement: str) -> None:  # R1
    path = f"{importer.replace('.', '/')}/x.py"
    sources = {path: statement, "admin/__init__.py": "", "admin/base/__init__.py": ""}
    [violation] = violations_of(sources)
    assert violation.startswith(f"{path}: {importer} must not import ")


# R4: admin の内部は一方向
@pytest.mark.parametrize(
    ("importer", "imported"),
    [
        ("admin/routers/x.py", "infrastructure.opensearch"),
        ("admin/routers/x.py", "infrastructure.crawler_client"),
        ("admin/routers/x.py", "admin.derivation"),
        ("admin/routers/x.py", "admin.crawler_mapping"),
        ("admin/routers/x.py", "admin.failures"),
        ("admin/routers/x.py", "admin"),  # 直下(`dependencies.py` など)への逆向きの依存
        ("admin/services/x.py", "admin.routers"),
        ("admin/services/x.py", "admin"),
        ("admin/derivation/x.py", "admin.schemas"),
        ("admin/derivation/x.py", "admin.services"),
        ("admin/derivation/x.py", "infrastructure.opensearch"),
        ("admin/derivation/x.py", "admin.failures"),
        ("admin/schemas/x.py", "admin.derivation"),
        ("admin/schemas/x.py", "admin.services"),
        ("admin/failures/x.py", "admin.schemas"),
        ("admin/failures/x.py", "admin.derivation"),
        ("admin/crawler_mapping/x.py", "infrastructure.opensearch"),
        ("admin/crawler_mapping/x.py", "infrastructure.probes"),
        ("admin/crawler_mapping/x.py", "admin.schemas"),
        ("admin/base/x.py", "admin.schemas"),
        ("admin/base/x.py", "admin.failures"),
        ("admin/base/x.py", "infrastructure.opensearch"),
    ],
)
def test_admin_internal_dependencies_run_in_one_direction(importer: str, imported: str) -> None:
    importer_module = module_of(dotted_name_of_file(importer))
    sources = {importer: f"import loreley_api.{imported}"}
    [violation] = violations_of(sources)
    assert violation.startswith(f"{importer}: {importer_module} must not import ")


@pytest.mark.parametrize(
    ("importer", "imported"),
    [
        ("admin/app.py", "admin.routers"),
        ("admin/app.py", "admin.base"),
        ("admin/dependencies.py", "admin.services"),
        ("admin/dependencies.py", "infrastructure.opensearch"),
        ("admin/routers/x.py", "admin.services"),
        ("admin/routers/x.py", "admin.schemas"),
        ("admin/routers/x.py", "admin.base"),
        ("admin/services/x.py", "admin.derivation"),
        ("admin/services/x.py", "admin.crawler_mapping"),
        ("admin/services/x.py", "admin.failures"),
        ("admin/services/x.py", "infrastructure.opensearch"),
        ("admin/services/x.py", "infrastructure.crawler_client"),
        ("admin/services/x.py", "infrastructure.probes"),
        ("admin/crawler_mapping/x.py", "admin.base"),
        ("admin/crawler_mapping/x.py", "infrastructure.crawler_client"),
        ("admin/failures/x.py", "admin.base"),
        ("admin/derivation/x.py", "admin.base"),
        ("admin/schemas/x.py", "admin.base"),
        ("admin/base/x.py", "common.http.errors"),
        ("admin/routers/x.py", "common.http.body"),
        ("config.py", "admin"),
        ("config.py", "infrastructure.opensearch"),
        ("main.py", "admin"),
        ("main.py", "infrastructure.crawler_client"),
    ],
)
def test_admin_allowed_dependencies_have_no_violations(importer: str, imported: str) -> None:
    sources = {
        importer: f"import loreley_api.{imported}",
        "admin/__init__.py": "",
        "infrastructure/__init__.py": "",
    }
    assert violations_of(sources) == []


def test_other_modules_must_not_import_the_admin_internals() -> None:  # R2・R3
    for importer in ("server/app.py", "health/router.py", "common/x.py", "main.py"):
        sources = {importer: "from loreley_api.admin.routers import create_admin_router"}
        [violation] = violations_of(sources)
        if importer == "main.py":
            assert "main must not import admin.routers" in violation
        else:
            assert f"{importer}: " in violation
            assert "must not import admin.routers" in violation


def test_admin_files_are_classified_by_their_place() -> None:
    assert module_of("admin") == "admin"
    assert module_of("admin.app") == "admin"
    assert module_of("admin.dependencies") == "admin"
    assert module_of("admin.settings") == "admin"
    assert module_of("admin.openapi_export") == "admin"
    for name in ADMIN_SUBMODULES:
        assert module_of(f"admin.{name}") == f"admin.{name}"
        assert module_of(f"admin.{name}.deep.module") == f"admin.{name}"
    # 未知のファイル・ディレクトリは、ルールの更新を促すため分類しない。
    assert module_of("admin.unknown") is None
    assert module_of("admin.unknown.x") is None
    assert module_of("admin.app.x") is None


def test_infrastructure_files_are_classified_by_their_place() -> None:
    assert module_of("infrastructure") == "namespace"
    for module in INFRASTRUCTURE_MODULES:
        assert module_of(f"{module}.x.y") == module
    assert module_of("infrastructure.unknown") is None


def test_an_unclassified_admin_or_infrastructure_file_is_a_violation() -> None:
    sources = {"admin/unknown/x.py": "", "infrastructure/unknown/x.py": ""}
    assert violations_of(sources) == [
        "admin/unknown/x.py: unclassified file (update dependency rules)",
        "infrastructure/unknown/x.py: unclassified file (update dependency rules)",
    ]


def test_a_cycle_inside_admin_is_detected() -> None:
    sources = {
        "admin/routers/a.py": "from loreley_api.admin.services import y",
        "admin/services/b.py": "from loreley_api.admin.routers import x",
        "admin/routers/__init__.py": "",
        "admin/services/__init__.py": "",
    }
    assert find_cycles(sources) == [["admin.routers", "admin.services", "admin.routers"]]


def test_a_cycle_between_modules_is_detected() -> None:
    sources = {
        "server/a.py": "from loreley_api.health import x",
        "health/b.py": "from loreley_api.server import y",
        "health/__init__.py": "",
        "server/__init__.py": "",
    }
    assert find_cycles(sources) == [["health", "server", "health"]]


def test_modules_without_cycles_are_not_reported() -> None:
    sources = {
        "main.py": "from loreley_api.server import create_app\nfrom loreley_api.health import x",
        "server/app.py": "from loreley_api.common import http",
        "health/router.py": "from loreley_api.common import http",
        "common/__init__.py": "",
        "server/__init__.py": "",
        "health/__init__.py": "",
    }
    assert find_cycles(sources) == []
