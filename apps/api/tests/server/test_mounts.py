"""マウントの口(ダミーのサブアプリ 2 つ)。AAM-U-2・0003 §3 を固定する。

サブアプリは自分の例外ハンドラ・最外殻の Starlette・ルーティングを持つ。マウントの下でも、
統一エラー形式・アクセスログ(1 リクエスト 1 行・マウントの接頭辞つきのテンプレート)・
`no-store`・想定外の例外の吸収(再送出しない)が成り立つことを確かめる。
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route

from loreley_api.server import SubAppMount, create_app
from tests.log_records import server_side_text
from tests.server.dummy_features import (
    SENTINEL_EXCEPTION,
    SENTINEL_ID,
    DummyResource,
    create_dummy_app,
)

PREFIX_A = "/api/dummy-a/v1"
PREFIX_B = "/api/dummy-b/v1"
ACCESS_LOGGER = "loreley_api.access"


def make_app(**kwargs) -> FastAPI:
    return create_app(
        mounts=[
            SubAppMount(PREFIX_A, create_dummy_app("a")),
            SubAppMount(PREFIX_B, create_dummy_app("b")),
        ],
        **kwargs,
    )


@pytest.fixture
def client() -> TestClient:
    """`raise_server_exceptions=True`: 例外が再送出されるなら、テストのクライアントまで上がる。"""
    return TestClient(make_app(), raise_server_exceptions=True)


@pytest.fixture
def logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG)
    return caplog


def error_of(response) -> dict:
    return response.json()["error"]


def access_lines(logs: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in logs.records if r.name == ACCESS_LOGGER]


def without_elapsed(line: str) -> str:
    return line.rsplit(" ", 1)[0]


# --- 正常な応答 ---


def test_a_mounted_route_responds_with_no_store(client: TestClient) -> None:
    response = client.get(f"{PREFIX_A}/items/{SENTINEL_ID}")

    assert response.status_code == 200
    assert response.json() == {"item_id": SENTINEL_ID}
    assert response.headers["cache-control"] == "no-store"


def test_the_two_mounts_do_not_interfere(
    client: TestClient, logs: pytest.LogCaptureFixture
) -> None:
    a = client.get(f"{PREFIX_A}/whoami")
    b = client.get(f"{PREFIX_B}/whoami")
    a_again = client.get(f"{PREFIX_A}/whoami")

    assert [r.json()["app"] for r in (a, b, a_again)] == ["a", "b", "a"]
    assert [without_elapsed(line) for line in access_lines(logs)] == [
        f"GET {PREFIX_A}/whoami 200",
        f"GET {PREFIX_B}/whoami 200",
        f"GET {PREFIX_A}/whoami 200",
    ]


def test_a_path_of_one_mount_is_not_served_by_the_other(client: TestClient) -> None:
    response = client.get(f"{PREFIX_B}/items/a")  # b にもある
    other = client.get("/api/dummy-c/v1/items/a")  # c はない

    assert response.status_code == 200
    assert other.status_code == 404


# --- アクセスログ(AAM-U-2) ---


def test_the_access_log_is_one_line_with_the_full_route_template(
    client: TestClient, logs: pytest.LogCaptureFixture
) -> None:
    """外側の middleware がサブアプリの処理の後に `scope["route"]`・`root_path`・`app_root_path` を
    読めるのは、Starlette の挙動による(FastAPI 0.165.0・Starlette 1.10.0 で確認)。
    このテストが壊れたら、このテストと `middleware.py` の `_route_template` を見る。
    """
    client.get(f"{PREFIX_A}/items/{SENTINEL_ID}", params={"q": "SENTINEL-QUERY"})

    (line,) = access_lines(logs)
    assert without_elapsed(line) == f"GET {PREFIX_A}/items/{{item_id}} 200"
    assert line.endswith("ms")
    assert "SENTINEL" not in server_side_text(logs.records)


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", "/items/a", 200),
        ("GET", "/nope", 404),
        ("POST", "/items/a", 405),
        ("GET", "/api-error", 409),
        ("GET", "/teapot", 418),
        ("POST", "/items", 400),
        ("GET", "/boom", 500),
    ],
)
def test_each_request_is_logged_exactly_once_whatever_the_outcome(
    client: TestClient, logs: pytest.LogCaptureFixture, method: str, path: str, status: int
) -> None:
    response = client.request(method, PREFIX_A + path, json={} if method == "POST" else None)

    assert response.status_code == status
    assert len(access_lines(logs)) == 1


def test_a_request_that_matches_no_route_under_a_mount_logs_a_dash(
    client: TestClient, logs: pytest.LogCaptureFixture
) -> None:
    client.get(f"{PREFIX_A}/SENTINEL-PATH/{SENTINEL_ID}")

    (line,) = access_lines(logs)
    assert without_elapsed(line) == "GET - 404"
    assert "SENTINEL" not in server_side_text(logs.records)


def test_a_request_that_stops_at_a_nested_mount_of_the_sub_app_logs_a_dash(
    logs: pytest.LogCaptureFixture,
) -> None:
    """`scope["route"]` が `Mount`(`Route`・`APIRoute` ではない)のままでも、パスを出さない。"""

    async def handler(_request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    sub_app = Starlette(routes=[Mount("/m", routes=[Route("/k/{id}", handler)])])
    # 型は `FastAPI` だが、素の `Starlette` でも動く(`Mount` を持つサブアプリの再現のため)。
    client = TestClient(create_app(mounts=[SubAppMount(PREFIX_A, sub_app)]))

    response = client.get(f"{PREFIX_A}/m/SENTINEL-PATH")

    assert response.status_code == 404
    (line,) = access_lines(logs)
    assert without_elapsed(line) == "GET - 404"
    assert "SENTINEL" not in server_side_text(logs.records)


def test_a_request_that_reaches_a_route_inside_a_nested_mount_logs_the_full_template(
    logs: pytest.LogCaptureFixture,
) -> None:
    """入れ子のマウントを通っても、実パス(ID)ではなく、接頭辞を重ねない完全なテンプレートを出す。

    サブアプリの接頭辞に、サブアプリ内の `Mount` の接頭辞(`/m`)が足される。
    """

    async def handler(_request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    sub_app = Starlette(routes=[Mount("/m", routes=[Route("/k/{id}", handler)])])
    client = TestClient(create_app(mounts=[SubAppMount(PREFIX_A, sub_app)]))

    response = client.get(f"{PREFIX_A}/m/k/{SENTINEL_ID}")

    assert response.status_code == 200
    (line,) = access_lines(logs)
    assert without_elapsed(line) == f"GET {PREFIX_A}/m/k/{{id}} 200"
    assert SENTINEL_ID not in server_side_text(logs.records)


def test_the_root_path_of_the_outer_app_is_not_part_of_the_logged_template(
    logs: pytest.LogCaptureFixture,
) -> None:
    """プロキシの配下(`root_path="/proxy"`)でも、テンプレートは外側の `root_path` を含まない。

    `scope["root_path"]` は外側の `root_path` を含む。マウントの接頭辞だけを足すには、
    `app_root_path`(マウントの手前の `root_path`)を引く必要がある。
    """
    client = TestClient(make_app(), root_path="/proxy")

    response = client.get(f"/proxy{PREFIX_A}/items/{SENTINEL_ID}")

    assert response.status_code == 200
    (line,) = access_lines(logs)
    assert without_elapsed(line) == f"GET {PREFIX_A}/items/{{item_id}} 200"
    assert SENTINEL_ID not in server_side_text(logs.records)


def test_no_store_is_set_by_the_path_seen_by_the_app_under_a_root_path() -> None:
    """`root_path` の配下でも、`/api/` の応答には `no-store` が付き、それ以外には付かない。

    `request.url.path` は `/proxy` を含むので、それで判定すると付かなくなる(レビュー指摘)。
    """
    client = TestClient(make_app(), root_path="/proxy")

    api_response = client.get(f"/proxy{PREFIX_A}/items/{SENTINEL_ID}")
    not_api_response = client.get("/proxy/nope")

    assert api_response.headers["cache-control"] == "no-store"
    assert not_api_response.status_code == 404
    assert "cache-control" not in not_api_response.headers


def test_a_mounted_route_is_logged_at_info_unless_it_is_a_debug_path(
    logs: pytest.LogCaptureFixture,
) -> None:
    client = TestClient(make_app(debug_access_log_paths={f"{PREFIX_A}/items/{{item_id}}"}))

    client.get(f"{PREFIX_A}/items/a")
    client.get(f"{PREFIX_B}/items/a")

    levels = [r.levelno for r in logs.records if r.name == ACCESS_LOGGER]
    assert levels == [logging.DEBUG, logging.INFO]


# --- 統一エラー形式(マウントの下) ---


def test_an_unknown_path_under_a_mount_is_a_json_404_with_no_store(client: TestClient) -> None:
    response = client.get(f"{PREFIX_A}/nope")

    assert response.status_code == 404
    assert error_of(response) == {
        "code": "not_found",
        "message": "the path is not defined",
        "retryable": False,
    }
    assert response.headers["cache-control"] == "no-store"


def test_the_404_of_a_mount_and_the_404_of_the_outer_app_have_the_same_shape(
    client: TestClient,
) -> None:
    inner = client.get(f"{PREFIX_A}/nope")
    outer = client.get("/api/nope")

    assert inner.json() == outer.json()
    assert inner.headers["content-type"] == outer.headers["content-type"]
    assert inner.headers["cache-control"] == outer.headers["cache-control"] == "no-store"


def test_an_undefined_method_under_a_mount_is_a_405_with_the_allow_header(
    client: TestClient,
) -> None:
    response = client.post(f"{PREFIX_A}/items/a")

    assert response.status_code == 405
    assert error_of(response)["code"] == "method_not_allowed"
    assert response.headers["allow"] == "GET"
    assert response.headers["cache-control"] == "no-store"


def test_an_api_error_under_a_mount_is_returned_as_given(client: TestClient) -> None:
    response = client.get(f"{PREFIX_A}/api-error")

    assert response.status_code == 409
    assert error_of(response) == {
        "code": "dummy_conflict",
        "message": "the dummy is in conflict",
        "retryable": True,
    }
    assert response.headers["cache-control"] == "no-store"


def test_another_http_exception_under_a_mount_is_an_http_error(client: TestClient) -> None:
    response = client.get(f"{PREFIX_A}/teapot")

    assert response.status_code == 418
    assert error_of(response)["code"] == "http_error"
    assert response.headers["cache-control"] == "no-store"
    assert SENTINEL_EXCEPTION not in response.text


def test_a_validation_error_under_a_mount_is_a_400_invalid_request(client: TestClient) -> None:
    response = client.post(f"{PREFIX_A}/items", json={"name": SENTINEL_ID, "count": 0})

    assert response.status_code == 400
    assert error_of(response) == {
        "code": "invalid_request",
        "message": "the request is invalid",
        "retryable": False,
        "details": {"errors": [{"field": "count", "reason": "range"}]},
    }
    assert SENTINEL_ID not in response.text
    assert response.headers["cache-control"] == "no-store"


# --- 想定外の例外(マウントの下) ---


def test_an_unexpected_exception_under_a_mount_is_a_500_and_is_not_raised_again(
    client: TestClient,
) -> None:
    """例外が上がらない(`raise_server_exceptions=True`)= サブアプリの最外殻が再送出していない。"""
    response = client.get(f"{PREFIX_A}/boom")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/json"
    assert error_of(response) == {
        "code": "internal_error",
        "message": "an internal error occurred",
        "retryable": False,
    }
    assert response.headers["cache-control"] == "no-store"
    assert SENTINEL_EXCEPTION not in response.text


def test_an_unexpected_exception_under_a_mount_is_logged_once_without_its_message(
    client: TestClient, logs: pytest.LogCaptureFixture
) -> None:
    client.get(f"{PREFIX_A}/boom")

    errors = [record for record in logs.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert (
        errors[0].getMessage().startswith("request failed unexpectedly: error=RuntimeError origin=")
    )
    assert errors[0].exc_info is None
    assert not errors[0].exc_text
    assert SENTINEL_EXCEPTION not in server_side_text(logs.records)
    (line,) = access_lines(logs)
    assert without_elapsed(line) == f"GET {PREFIX_A}/boom 500"


def test_the_other_mount_keeps_serving_after_an_unexpected_exception(client: TestClient) -> None:
    client.get(f"{PREFIX_A}/boom")

    assert client.get(f"{PREFIX_A}/whoami").status_code == 200
    assert client.get(f"{PREFIX_B}/whoami").status_code == 200


# --- マウントのパスと末尾スラッシュ(A 5.1) ---


@pytest.mark.parametrize(
    "path",
    [
        PREFIX_A,  # 末尾スラッシュなしのマウント位置
        f"{PREFIX_A}/",  # 末尾スラッシュつきのマウント位置
        f"{PREFIX_A}/items/a/",  # ルートの末尾スラッシュ
        f"{PREFIX_A}/whoami/",
    ],
)
def test_a_trailing_slash_or_the_mount_path_itself_is_a_json_404(
    client: TestClient, path: str
) -> None:
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 404
    assert error_of(response)["code"] == "not_found"


def test_a_mounted_app_never_redirects_even_when_it_was_created_with_the_default() -> None:
    sub_app = create_dummy_app("default", redirect_slashes=True)
    client = TestClient(create_app(mounts=[SubAppMount(PREFIX_A, sub_app)]))

    response = client.get(f"{PREFIX_A}/items/a/", follow_redirects=False)

    assert response.status_code == 404
    assert "location" not in response.headers


# --- lifespan(0003 §3。製品コードに終了処理の仕組みは足さない) ---


def test_a_resource_of_the_parent_lifespan_is_usable_by_a_mounted_app_while_it_runs() -> None:
    resource = DummyResource()
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        resource.is_open = True
        events.append("start")
        try:
            yield
        finally:
            resource.is_open = False
            events.append("stop")

    app = create_app(
        mounts=[SubAppMount(PREFIX_A, create_dummy_app("a", resource=resource))],
        lifespan=lifespan,
    )

    assert not resource.is_open
    with TestClient(app) as client:
        assert client.get(f"{PREFIX_A}/whoami").json() == {"app": "a", "resource_open": True}
        client.get(f"{PREFIX_A}/whoami")
        assert events == ["start"]
    assert not resource.is_open
    assert events == ["start", "stop"]


def test_the_lifespan_of_a_mounted_app_itself_is_not_run() -> None:
    """Starlette はマウントしたサブアプリの lifespan を実行しない。

    サブアプリが閉じる資源(クライアントなど)は、`create_app(lifespan=...)` に渡す。
    admin 実装時の注意の根拠を固定する。
    """
    events: list[str] = []

    @asynccontextmanager
    async def sub_lifespan(_app: FastAPI) -> AsyncIterator[None]:
        events.append("sub-start")
        yield
        events.append("sub-stop")

    app = create_app(mounts=[SubAppMount(PREFIX_A, create_dummy_app("a", lifespan=sub_lifespan))])

    with TestClient(app) as client:
        assert client.get(f"{PREFIX_A}/whoami").status_code == 200
    assert events == []
