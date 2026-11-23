"""`admin/derivation` は純粋(D 6章 R7。C 5章冒頭)。

時計・I/O・乱数・環境変数・pydantic を使わない。時刻は引数 `now` で受ける。実ソースの検査と、
検査器自体が違反を検出できることの合成ソースでの確認(正例・負例。ルールが空振りしていないこと)。

検査は import 文(相対 import は絶対名に直す)と、呼び出しの名前(`now()`・`open()` など)の AST。
`schemas`・`services`・`infrastructure` を import しないことは、依存ルール(R4)のテストが検査する。
限界: 動的な import(`importlib`・`__import__` の文字列)と、別名を経由した呼び出し
(`clock = datetime.now; clock()`)は検出できない。時刻を引数で受けることは、各導出の単体テスト
(固定時刻)が確かめる。
"""

import ast
from pathlib import Path

import pytest

from tests.architecture.dependency_rules import absolute_base_of_from_import

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "loreley_api"
DERIVATION_DIRECTORY = PACKAGE_ROOT / "admin" / "derivation"
# 合成ソースの、置かれている場所(相対 import の解決に使う)。
SYNTHETIC_PATH = "admin/derivation/synthetic.py"

# import してはいけないモジュール(ドット名の接頭辞で一致させる)。
FORBIDDEN_MODULES: dict[str, str] = {
    "pydantic": "pydantic",
    "pydantic_settings": "pydantic",
    "fastapi": "HTTP framework",
    "starlette": "HTTP framework",
    "time": "clock",
    "sched": "clock",
    "zoneinfo": "time zone database (I/O)",
    "random": "randomness",
    "secrets": "randomness",
    "uuid": "randomness",
    "os": "environment variables and I/O",
    "sys": "environment and I/O",
    "pathlib": "I/O",
    "io": "I/O",
    "shutil": "I/O",
    "tempfile": "I/O",
    "subprocess": "I/O",
    "socket": "I/O",
    "ssl": "I/O",
    "urllib": "I/O",
    "http": "I/O",
    "asyncio": "I/O",
    "threading": "I/O",
    "logging": "I/O",
    "anyio": "I/O",
    "opensearchpy": "I/O",
    "urllib3": "I/O",
    "httpx": "I/O",
    "requests": "I/O",
    "loreley_api.common.clock": "clock",
    "loreley_api.common.concurrency": "I/O",
    "loreley_api.common.http": "I/O",
    "loreley_api.common.logging_setup": "I/O",
    "loreley_api.config": "environment variables",
}
# 呼び出してはいけない関数(名前)。
FORBIDDEN_FUNCTION_CALLS = frozenset(
    {"open", "print", "input", "exec", "eval", "compile", "__import__"}
)
# 現在時刻を取るメソッド(`datetime.now()`・`datetime.datetime.utcnow()` など)。
FORBIDDEN_METHOD_CALLS = frozenset({"now", "utcnow", "today"})


def imported_names(tree: ast.AST, relative_path: str) -> list[str]:
    """import 文が取り込むものの絶対のドット名。`from a.b import c` は `a.b` と `a.b.c`。"""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = absolute_base_of_from_import(node, relative_path)
            if not base:
                continue
            names.append(base)
            names.extend(f"{base}.{alias.name}" for alias in node.names)
    return names


def forbidden_reason(imported: str) -> str | None:
    for module, reason in FORBIDDEN_MODULES.items():
        if imported == module or imported.startswith(f"{module}."):
            return reason
    return None


def purity_violations(source: str, relative_path: str = SYNTHETIC_PATH) -> list[str]:
    tree = ast.parse(source)
    violations = [
        f"imports {name} ({reason})"
        for name in imported_names(tree, relative_path)
        if (reason := forbidden_reason(name)) is not None
    ]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_FUNCTION_CALLS:
            violations.append(f"line {node.lineno}: calls {node.func.id}()")
        if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_METHOD_CALLS:
            violations.append(f"line {node.lineno}: calls .{node.func.attr}() (reads the clock)")
    return violations


def derivation_sources() -> dict[str, str]:
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(DERIVATION_DIRECTORY.glob("*.py"))
    }


# --- 実際のソース ---


def test_the_derivation_files_are_found() -> None:
    names = set(derivation_sources())

    assert {
        "values.py",
        "lock_state.py",
        "stalled.py",
        "rerun.py",
        "job_view.py",
        "deletion_view.py",
        "source_summary.py",
        "settings_view.py",
        "units.py",
        "cluster_view.py",
    } <= names


def test_actual_derivation_sources_are_pure() -> None:
    violations = {
        name: found
        for name, source in derivation_sources().items()
        if (found := purity_violations(source, f"admin/derivation/{name}"))
    }

    assert violations == {}


# --- 検査器の自己テスト(合成ソース) ---


@pytest.mark.parametrize(
    "statement",
    [
        "import pydantic",
        "from pydantic import BaseModel",
        "import pydantic_settings",
        "import time",
        "from time import monotonic",
        "import random",
        "from secrets import token_hex",
        "import uuid",
        "import os",
        "from os import environ",
        "import os.path",
        "import sys",
        "import pathlib",
        "from pathlib import Path",
        "import socket",
        "import logging",
        "import asyncio",
        "import anyio",
        "import fastapi",
        "from fastapi import Depends",
        "import opensearchpy",
        "import urllib3",
        "import urllib.request",
        "import zoneinfo",
        "from loreley_api.common.clock import Clock",
        "from loreley_api.common import clock",
        "import loreley_api.common.concurrency",
        "from loreley_api.common.http import errors",
        "from loreley_api.config import load_config",
        # 相対 import は、置かれている場所から絶対名に直して検査する。
        "from ...common.clock import Clock",
        "from ...common import clock",
        "from ... import config",
        "from ...config import load_config",
    ],
)
def test_a_forbidden_import_is_detected(statement: str) -> None:
    assert purity_violations(statement) != []


@pytest.mark.parametrize(
    "statement",
    [
        "from datetime import datetime, timedelta",
        "import datetime",
        "from decimal import Decimal",
        "import math",
        "import re",
        "from enum import StrEnum",
        "from dataclasses import dataclass",
        "from collections.abc import Mapping",
        "from loreley_api.common.timestamps import format_instant",
        "from loreley_api.common.results import Failed",
        "from loreley_api.admin.base.codes import JobStatus",
        "from ...common.timestamps import format_instant",
        "from ..base.codes import JobStatus",
        "from . import values",
        # 名前が似ているだけのモジュールは対象ではない。
        "import timeit_helpers",
        "import osmosis",
    ],
)
def test_a_pure_import_is_accepted(statement: str) -> None:
    assert purity_violations(statement) == []


@pytest.mark.parametrize(
    "call",
    [
        "datetime.now()",
        "datetime.now(UTC)",
        "datetime.datetime.utcnow()",
        "date.today()",
        "clock.now()",
        "open('x')",
        "print('x')",
        "input()",
        "eval('1')",
        "__import__('os')",
    ],
)
def test_a_clock_or_io_call_is_detected(call: str) -> None:
    assert purity_violations(f"value = {call}\n") != []


def test_a_function_that_takes_now_as_an_argument_is_accepted() -> None:
    source = (
        "from datetime import datetime\n"
        "def is_expired(lease: datetime, now: datetime) -> bool:\n"
        "    return now >= lease\n"
    )

    assert purity_violations(source) == []


def test_a_violation_inside_a_function_is_detected() -> None:
    source = "def f():\n    import random\n    return random.random()\n"

    assert purity_violations(source) == ["imports random (randomness)"]


def test_the_message_names_the_line_of_a_call() -> None:
    assert purity_violations("\n\nx = datetime.now()\n") == [
        "line 3: calls .now() (reads the clock)"
    ]
