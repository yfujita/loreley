"""HTTP の規約(D 6章 R9・R10)の AST 検査。

- CORS を許可しない: `fastapi.middleware.cors`・`starlette.middleware.cors` を import しない。
- ルート関数と、`Depends` に渡す依存関係は `async def`(同期の関数は共通のスレッドプールで動き、
  並行の上限を迂回するため)。
- `FastAPI(...)` は、`docs_url=None`・`redoc_url=None`・`redirect_slashes=False` を明示する。
  `openapi_url` も明示する(値は問わない)。

制約: import 文と、デコレーターが `<名前>.<HTTP メソッド>(...)` の形のルート関数だけが対象。
動的な import やデコレーターを変数に入れた登録は検出できない。`Depends` の検査は、引数の関数を
**名前だけで**パッケージ内の定義に結び付ける(同名の別の関数は区別できない)。クラスを渡した
依存関係・名前でない式(`Depends(factory()())` など)・別名での登録(`dep = Depends; dep(f)`)は
検出できない。引数が呼び出し(ファクトリー `Depends(make_dep(...))`)のときは、ファクトリーが
`return` する入れ子の関数を調べる。
"""

import ast
from collections.abc import Mapping
from dataclasses import dataclass
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


DEPENDENCY_FUNCTION_NAMES = {"Depends", "Security"}


@dataclass(frozen=True)
class DependencyUse:
    path: str
    line: int
    argument: ast.expr


def _is_dependency_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id in DEPENDENCY_FUNCTION_NAMES) or (
        isinstance(func, ast.Attribute) and func.attr in DEPENDENCY_FUNCTION_NAMES
    )


def find_dependency_uses(sources: Mapping[str, str]) -> list[DependencyUse]:
    """`Depends(<依存関係>)` の使用箇所。引数のない `Depends()` は対象外。"""
    uses: list[DependencyUse] = []
    for path, source in sources.items():
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.Call) and _is_dependency_call(node)):
                continue
            keywords = {kw.arg: kw.value for kw in node.keywords}
            argument = node.args[0] if node.args else keywords.get("dependency")
            if argument is not None:
                uses.append(DependencyUse(path, node.lineno, argument))
    return uses


def _function_definitions(
    sources: Mapping[str, str],
) -> dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]]:
    definitions: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    for source in sources.values():
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                definitions.setdefault(node.name, []).append(node)
    return definitions


def _name_of(expression: ast.expr) -> str | None:
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Attribute):
        return expression.attr
    return None


def _returned_nested_functions(
    factory: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """ファクトリーの中で定義され、`return <名前>` で返される関数。"""
    returned_names = {
        node.value.id
        for node in ast.walk(factory)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Name)
    }
    return [
        node
        for node in ast.walk(factory)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node is not factory
        and node.name in returned_names
    ]


def find_sync_dependencies(sources: Mapping[str, str]) -> list[str]:
    """`Depends` に渡された、同期の関数(`def`)・ラムダ。"""
    definitions = _function_definitions(sources)
    problems: list[str] = []
    for use in find_dependency_uses(sources):
        where = f"{use.path}:{use.line}"
        argument = use.argument
        if isinstance(argument, ast.Lambda):
            problems.append(f"{where} Depends(lambda) is not async def")
        elif isinstance(argument, ast.Call):
            factory_name = _name_of(argument.func)
            candidates = [
                nested
                for factory in definitions.get(factory_name or "", [])
                for nested in _returned_nested_functions(factory)
            ]
            problems += [
                f"{where} Depends({factory_name}(...)) returns the sync function {nested.name}"
                for nested in candidates
                if isinstance(nested, ast.FunctionDef)
            ]
        elif (name := _name_of(argument)) is not None:
            problems += [
                f"{where} Depends({name}) is not async def"
                for definition in definitions.get(name, [])
                if isinstance(definition, ast.FunctionDef)
            ]
    return problems


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


def test_dependencies_passed_to_depends_are_all_async() -> None:  # R9
    sources = load_package_sources()

    # 空振りしていないことの確認(`request_input.py` の `Depends(...)` が見つかる)。
    used_in = {use.path for use in find_dependency_uses(sources)}
    assert "admin/routers/request_input.py" in used_in
    assert find_sync_dependencies(sources) == []


def test_every_fastapi_call_states_the_http_defaults_explicitly() -> None:
    sources = load_package_sources()

    # 空振りしていないことの確認(外側の `create_app` とサブアプリの `FastAPI(...)` が見つかる)。
    found_in = [call.split(":")[0] for call in find_fastapi_calls(sources)]
    assert {"server/app.py", "admin/app.py"} <= set(found_in)
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


# --- R9: `Depends` の関数が `async def`(自己テスト) ---


def test_a_sync_dependency_is_detected() -> None:
    source = (
        "def read_id(): ...\n"
        "async def handler(x: Annotated[str, Depends(read_id)]): ...\n"
        "router.get('/', dependencies=[Depends(read_id)])\n"
    )
    problems = find_sync_dependencies({"a.py": source})
    assert len(problems) == 2
    assert all("Depends(read_id) is not async def" in problem for problem in problems)


def test_an_async_dependency_is_not_reported() -> None:
    source = "async def read_id(): ...\nasync def handler(x: str = Depends(read_id)): ...\n"
    assert find_sync_dependencies({"a.py": source}) == []


def test_a_sync_dependency_defined_in_another_file_is_detected() -> None:
    sources = {
        "deps.py": "def read_id(): ...\n",
        "routes.py": "async def h(x: str = Depends(deps.read_id)): ...\n",
    }
    assert len(find_sync_dependencies(sources)) == 1


@pytest.mark.parametrize("function_name", ["Depends", "Security"])
def test_the_dependency_keyword_argument_is_checked(function_name: str) -> None:
    source = f"def read_id(): ...\nx = {function_name}(dependency=read_id)\n"
    assert len(find_sync_dependencies({"a.py": source})) == 1


def test_a_lambda_dependency_is_detected() -> None:
    assert len(find_sync_dependencies({"a.py": "x = Depends(lambda: 1)"})) == 1


def test_a_factory_that_returns_a_sync_function_is_detected() -> None:
    source = "def make(limit):\n    def read(): ...\n    return read\nx = Depends(make(3))\n"
    [problem] = find_sync_dependencies({"a.py": source})
    assert "Depends(make(...)) returns the sync function read" in problem


def test_a_factory_that_returns_an_async_function_is_not_reported() -> None:
    source = (
        "def make(limit):\n"
        "    def helper(): ...\n"
        "    async def read(): ...\n"
        "    return read\n"
        "x = Depends(make(3))\n"
    )
    assert find_sync_dependencies({"a.py": source}) == []


def test_depends_without_an_argument_and_unknown_functions_are_ignored() -> None:
    source = "x: Model = Depends()\ny = Depends(library_function)\nz = Depends(make())\n"
    assert find_sync_dependencies({"a.py": source}) == []
    assert len(find_dependency_uses({"a.py": source})) == 2
