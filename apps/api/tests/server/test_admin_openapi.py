"""Admin API の OpenAPI の公開(`OPENAPI_ENABLED`。A 5.4・BAPI-P-4。C 11章 15)。

外側のアプリにマウントした形で、サブアプリ側の `/api/admin/v1/openapi.json` を確かめる。
既定(無効)は JSON の 404、`OPENAPI_ENABLED=true` のときだけ JSON が出る。`/docs`・`/redoc` は常に
無効で、外側のアプリは `/openapi.json` を出さない。`OPENAPI_ENABLED` は、ほかの挙動を変えない。
"""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from loreley_api.admin import ADMIN_API_PREFIX, create_admin_app
from loreley_api.admin.openapi_export import render_openapi_json
from loreley_api.health import create_health_router
from loreley_api.server import SubAppMount, create_app
from tests.admin.factories import make_admin_dependencies
from tests.admin.write_requests import register_body
from tests.fakes.clock import FixedClock
from tests.fakes.fake_crawler_client import FakeCrawlerClient
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.fakes.inline_runner import InlineRunner
from tests.openapi_structure import structure_problems

OPENAPI_URL = f"{ADMIN_API_PREFIX}/openapi.json"
NEVER_PUBLISHED_PATHS = [
    "/docs",
    "/redoc",
    "/openapi.json",
    "/docs/oauth2-redirect",
    f"{ADMIN_API_PREFIX}/docs",
    f"{ADMIN_API_PREFIX}/redoc",
    f"{ADMIN_API_PREFIX}/docs/oauth2-redirect",
]


def make_client(*, openapi_enabled: bool) -> TestClient:
    deps = make_admin_dependencies(
        InMemoryReaders(), FixedClock(), InlineRunner(), crawler=FakeCrawlerClient()
    )
    app = create_app(
        routers=[create_health_router()],
        mounts=[
            SubAppMount(ADMIN_API_PREFIX, create_admin_app(deps, openapi_enabled=openapi_enabled))
        ],
    )
    return TestClient(app)


def error_code_of(response: Any) -> str:
    assert response.headers["content-type"] == "application/json"
    return response.json()["error"]["code"]


# --- 既定(無効) ---


def test_the_openapi_json_is_a_json_404_by_default() -> None:
    response = make_client(openapi_enabled=False).get(OPENAPI_URL)

    assert response.status_code == 404
    assert error_code_of(response) == "not_found"


def test_the_openapi_is_disabled_when_the_argument_is_omitted() -> None:
    """`create_admin_app` の既定は無効(`main` が設定を渡さない限り公開しない)。"""
    deps = make_admin_dependencies(InMemoryReaders(), FixedClock(), InlineRunner())
    app = create_app(mounts=[SubAppMount(ADMIN_API_PREFIX, create_admin_app(deps))])

    assert TestClient(app).get(OPENAPI_URL).status_code == 404


# --- 有効 ---


def test_the_openapi_json_is_published_only_when_enabled() -> None:
    response = make_client(openapi_enabled=True).get(OPENAPI_URL)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["openapi"].startswith("3.")
    assert structure_problems(body) == []


def test_the_published_json_is_the_same_document_as_the_export() -> None:
    """公開と書き出しで内容が違うと、型生成の入力と実際の API の説明が食い違う。

    FastAPI は公開時にだけ `servers` に `root_path` を足す(既定)ので、固定してある(BAPI-U-2)。
    """
    published = make_client(openapi_enabled=True).get(OPENAPI_URL).json()

    assert published == json.loads(render_openapi_json())
    assert published["servers"] == [{"url": ADMIN_API_PREFIX}]


def test_the_published_json_does_not_change_between_requests() -> None:
    client = make_client(openapi_enabled=True)

    assert client.get(OPENAPI_URL).json() == client.get(OPENAPI_URL).json()


def test_a_trailing_slash_on_the_openapi_path_is_a_json_404_even_when_enabled() -> None:
    response = make_client(openapi_enabled=True).get(f"{OPENAPI_URL}/", follow_redirects=False)

    assert response.status_code == 404
    assert error_code_of(response) == "not_found"


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
def test_the_openapi_path_accepts_only_get_when_enabled(method: str) -> None:
    response = getattr(make_client(openapi_enabled=True), method)(OPENAPI_URL)

    assert response.status_code == 405
    assert error_code_of(response) == "method_not_allowed"


# --- 常に公開しないもの ---


@pytest.mark.parametrize("openapi_enabled", [False, True])
@pytest.mark.parametrize("path", NEVER_PUBLISHED_PATHS)
def test_the_docs_and_the_outer_openapi_are_never_published(
    path: str, openapi_enabled: bool
) -> None:
    response = make_client(openapi_enabled=openapi_enabled).get(path)

    assert response.status_code == 404
    assert error_code_of(response) == "not_found"


# --- `OPENAPI_ENABLED` はほかの挙動を変えない ---

# (メソッド, パス, 送る引数)。正常・検証の失敗・未定義のパス・許可外のメソッド・書き込みを含む。
OTHER_REQUESTS: list[tuple[str, str, dict[str, Any]]] = [
    ("get", "/healthz", {}),
    ("get", f"{ADMIN_API_PREFIX}/meta", {}),
    ("get", f"{ADMIN_API_PREFIX}/sources", {}),
    ("get", f"{ADMIN_API_PREFIX}/sources", {"params": {"unknown": "1"}}),
    ("get", f"{ADMIN_API_PREFIX}/sources/no-such-source", {}),
    ("get", f"{ADMIN_API_PREFIX}/jobs", {"params": {"page": "0"}}),
    ("get", f"{ADMIN_API_PREFIX}/NO-SUCH-PATH", {}),
    ("get", f"{ADMIN_API_PREFIX}/meta/", {}),
    ("delete", f"{ADMIN_API_PREFIX}/meta", {}),
    ("post", f"{ADMIN_API_PREFIX}/sources", {"json": register_body()}),
    ("post", f"{ADMIN_API_PREFIX}/sources", {"content": b"{", "headers": {"Origin": "http://x"}}),
    ("options", f"{ADMIN_API_PREFIX}/sources", {"headers": {"Origin": "http://x"}}),
]


@pytest.mark.parametrize(("method", "path", "arguments"), OTHER_REQUESTS)
def test_the_openapi_setting_changes_no_other_response(
    method: str, path: str, arguments: dict[str, Any]
) -> None:
    def respond(openapi_enabled: bool) -> tuple[int, dict[str, str], bytes]:
        response = getattr(make_client(openapi_enabled=openapi_enabled), method)(path, **arguments)
        return response.status_code, dict(response.headers), response.content

    disabled_status, disabled_headers, disabled_body = respond(False)
    enabled_status, enabled_headers, enabled_body = respond(True)

    assert (enabled_status, enabled_body) == (disabled_status, disabled_body)
    # ヘッダーの値は、時刻に由来する `date` などを除き、挙動に関わるものだけを比べる。
    assert enabled_headers.keys() == disabled_headers.keys()
    for name in ("content-type", "cache-control", "allow"):
        assert enabled_headers.get(name) == disabled_headers.get(name)
