"""依存ルールのテスト(0002 3.2)。

実際のソースツリー全体を検査するテストと、検査器自体が違反を検出できることを
合成ソースで確かめるテスト(まだ存在しない機能パッケージ `admin` などに対しても、ルールが
効くことの確認)に分かれる。
"""

from pathlib import Path

import pytest

from tests.architecture.dependency_rules import (
    COMMON,
    FEATURE_PACKAGES,
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
    assert {"main.py", "config.py", "server/app.py", "health/router.py"} <= set(sources)
    assert "common/http/middleware.py" in sources


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


def test_health_is_a_feature_package() -> None:
    assert "health" in FEATURE_PACKAGES  # admin などを足しても、書き換えなくてよい


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


def test_only_main_may_import_the_feature_packages() -> None:
    importers = {
        module
        for module, allowed in build_allowed().items()
        if allowed & FEATURE_PACKAGES  # 機能パッケージを import できるモジュール
    }
    assert importers == {"main"}


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
        "import opensearchpy",
        "from opensearchpy import OpenSearch",
        "import urllib3",
        "from urllib3.exceptions import HTTPError",
        "import requests",
        "import httpx",
        "import httpx2",
        "from httpx2 import Client",
        "import aiohttp",
        "import anyio",
        "from anyio import to_thread",
    ],
)
@pytest.mark.parametrize("path", ["main.py", "server/app.py", "health/router.py", "common/x.py"])
def test_no_module_may_import_an_external_access_library(path: str, statement: str) -> None:
    """基盤は外部システムへ接続するライブラリを使わない(所有者なし)。"""
    [violation] = violations_of({path: statement})
    assert violation.startswith(f"{path}: ")
    assert "must not import" in violation
    assert "no module" in violation


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
