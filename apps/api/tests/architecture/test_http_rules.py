"""HTTP の規約(D 6章 R9・R10 の基盤の部分)の AST 検査。

- CORS を許可しない: `fastapi.middleware.cors`・`starlette.middleware.cors` を import しない。
- ルート関数は `async def`(同期の関数は共通のスレッドプールで動き、並行の上限を迂回するため)。
- `FastAPI(...)` は、`docs_url=None`・`redoc_url=None`・`redirect_slashes=False` を明示する。
  `openapi_url` も明示する(値は問わない)。

制約: import 文と、デコレーターが `<名前>.<HTTP メソッド>(...)` の形のルート関数だけが対象。
動的な import やデコレーターを変数に入れた登録は検出できない。
"""

import ast
from collections.abc import Mapping
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "loreley_api"

CORS_MODULES = {"fastapi.middleware.cors", "starlette.middleware.cors"}
ROUTE_DECORATOR_NAMES = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "trace",
    "api_route",
    "websocket",
}
# `FastAPI(...)` に明示するキーワード引数と、その値(`ast.Constant` の値)。
REQUIRED_FASTAPI_ARGUMENTS: dict[str, object] = {
    "docs_url": None,
    "redoc_url": None,
    "redirect_slashes": False,
}
# `FastAPI(...)` に、書いてあること自体を検査するキーワード引数(値は問わない)。
EXPLICIT_FASTAPI_ARGUMENTS = ("openapi_url",)


def load_package_sources() -> dict[str, str]:
    return {
        path.relative_to(PACKAGE_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in PACKAGE_ROOT.rglob("*.py")
    }


def find_cors_imports(sources: Mapping[str, str]) -> list[str]:
    found: list[str] = []
    for path, source in sources.items():
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                found += [
                    f"{path}: {alias.name}" for alias in node.names if alias.name in CORS_MODULES
                ]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported_modules = [node.module, *(f"{node.module}.{a.name}" for a in node.names)]
                found += [f"{path}: {name}" for name in imported_modules if name in CORS_MODULES]
    return found


def _is_route_decorator(decorator: ast.expr) -> bool:
    return (
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr in ROUTE_DECORATOR_NAMES
    )


def find_sync_route_functions(sources: Mapping[str, str]) -> list[str]:
    return [
        f"{path}:{node.lineno} {node.name}"
        for path, source in sources.items()
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and any(map(_is_route_decorator, node.decorator_list))
    ]


def find_route_functions(sources: Mapping[str, str]) -> list[str]:
    """ルート関数(`async def` を含む)。検査が空振りしていないことの確認用。"""
    return [
        f"{path}:{node.name}"
        for path, source in sources.items()
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and any(map(_is_route_decorator, node.decorator_list))
    ]


def _is_fastapi_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and (
        (isinstance(node.func, ast.Name) and node.func.id == "FastAPI")
        or (isinstance(node.func, ast.Attribute) and node.func.attr == "FastAPI")
    )


def find_fastapi_calls(sources: Mapping[str, str]) -> list[str]:
    return [
        f"{path}:{node.lineno}"
        for path, source in sources.items()
        for node in ast.walk(ast.parse(source))
        if _is_fastapi_call(node)
    ]


def find_fastapi_calls_missing_arguments(sources: Mapping[str, str]) -> list[str]:
    problems: list[str] = []
    for path, source in sources.items():
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.Call) and _is_fastapi_call(node)):
                continue
            keywords = {kw.arg: kw.value for kw in node.keywords}
            for name, expected in REQUIRED_FASTAPI_ARGUMENTS.items():
                value = keywords.get(name)
                is_explicit = isinstance(value, ast.Constant) and value.value is expected
                if not is_explicit:
                    problems.append(f"{path}:{node.lineno} FastAPI(...) needs {name}={expected!r}")
            problems += [
                f"{path}:{node.lineno} FastAPI(...) needs {name}=<explicit>"
                for name in EXPLICIT_FASTAPI_ARGUMENTS
                if name not in keywords
            ]
    return problems


# --- 実際のソースツリー ---


def test_no_module_imports_cors_middleware() -> None:
    assert find_cors_imports(load_package_sources()) == []


def test_route_functions_are_found_and_all_are_async() -> None:
    sources = load_package_sources()

    assert "health/router.py:healthz" in find_route_functions(sources)  # 空振りしていない
    assert find_sync_route_functions(sources) == []


def test_every_fastapi_call_states_the_http_defaults_explicitly() -> None:
    sources = load_package_sources()

    # 空振りしていないことの確認(`create_app` の `FastAPI(...)` が見つかる)。
    assert "server/app.py" in [call.split(":")[0] for call in find_fastapi_calls(sources)]
    assert find_fastapi_calls_missing_arguments(sources) == []


# --- 検査器の自己テスト(合成ソース) ---


@pytest.mark.parametrize(
    "statement",
    [
        "from fastapi.middleware.cors import CORSMiddleware",
        "from starlette.middleware.cors import CORSMiddleware",
        "import fastapi.middleware.cors",
        "from fastapi.middleware import cors",
        "from starlette.middleware import cors",
    ],
)
def test_cors_imports_are_detected(statement: str) -> None:
    assert len(find_cors_imports({"server/app.py": statement})) == 1


def test_other_middleware_imports_are_not_cors() -> None:
    sources = {
        "a.py": "from starlette.middleware.base import BaseHTTPMiddleware\n"
        "from fastapi.middleware.gzip import GZipMiddleware"
    }
    assert find_cors_imports(sources) == []


@pytest.mark.parametrize("method", sorted(ROUTE_DECORATOR_NAMES))
@pytest.mark.parametrize("owner", ["router", "app", "self.router"])
def test_a_sync_route_function_is_detected(owner: str, method: str) -> None:
    source = f"@{owner}.{method}('/x')\ndef handler():\n    return 1\n"
    assert len(find_sync_route_functions({"a.py": source})) == 1


def test_async_route_functions_and_plain_functions_are_not_reported() -> None:
    source = (
        "@router.get('/x')\n"
        "async def handler():\n"
        "    return 1\n"
        "\n"
        "@some_decorator\n"
        "def helper():\n"
        "    return 2\n"
        "\n"
        "@functools.cache\n"
        "def cached():\n"
        "    return 3\n"
    )
    assert find_sync_route_functions({"a.py": source}) == []


def test_a_sync_route_function_nested_in_a_factory_is_detected() -> None:
    source = (
        "def create_router():\n"
        "    router = APIRouter()\n"
        "    @router.get('/x')\n"
        "    def handler():\n"
        "        return 1\n"
        "    return router\n"
    )
    assert len(find_sync_route_functions({"a.py": source})) == 1


ALL_NAMES = [*REQUIRED_FASTAPI_ARGUMENTS, *EXPLICIT_FASTAPI_ARGUMENTS]


def fastapi_call_without(name: str | None = None, **overrides: str) -> str:
    """必要なキーワードをすべて書いた `FastAPI(...)`。`name` を省き、`overrides` で値を替える。"""
    values = {**REQUIRED_FASTAPI_ARGUMENTS, "openapi_url": None} | overrides
    arguments = ", ".join(f"{key}={value}" for key, value in values.items() if key != name)
    return f"app = FastAPI({arguments})"


def test_a_fastapi_call_with_all_the_defaults_is_accepted() -> None:
    source = fastapi_call_without(lifespan="x")
    assert find_fastapi_calls_missing_arguments({"a.py": source}) == []


def test_the_value_of_openapi_url_is_not_checked() -> None:
    source = fastapi_call_without(openapi_url="'/openapi.json'")
    assert find_fastapi_calls_missing_arguments({"a.py": source}) == []


@pytest.mark.parametrize("missing", ALL_NAMES)
def test_a_fastapi_call_without_an_explicit_default_is_detected(missing: str) -> None:
    problems = find_fastapi_calls_missing_arguments({"a.py": fastapi_call_without(missing)})

    assert len(problems) == 1
    assert f" needs {missing}=" in problems[0]


@pytest.mark.parametrize(
    "argument", ["docs_url='/docs'", "redoc_url='/redoc'", "redirect_slashes=True"]
)
def test_a_fastapi_call_with_a_non_default_value_is_detected(argument: str) -> None:
    name, value = argument.split("=")

    problems = find_fastapi_calls_missing_arguments({"a.py": fastapi_call_without(**{name: value})})

    assert len(problems) == 1
    assert name in problems[0]


def test_a_bare_fastapi_call_reports_every_missing_argument() -> None:
    assert len(find_fastapi_calls_missing_arguments({"a.py": "FastAPI()"})) == len(ALL_NAMES)


def test_a_qualified_fastapi_call_is_also_checked() -> None:
    sources = {"a.py": "fastapi.FastAPI()"}
    assert len(find_fastapi_calls_missing_arguments(sources)) == len(ALL_NAMES)
