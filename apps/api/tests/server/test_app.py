import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from loreley_api.server import create_app
from tests.log_records import server_side_text
from tests.server.dummy_features import (
    SENTINEL_EXCEPTION,
    SENTINEL_ID,
    DummyResource,
    create_dummy_router,
)


def error_of(response) -> dict:
    return response.json()["error"]


@pytest.fixture
def client() -> TestClient:
    app = create_app(routers=[create_dummy_router(path_prefix="/dummy")])
    return TestClient(app, raise_server_exceptions=True)


# --- 外側のアプリの設定(A 2.2・5.1・5.4) ---


def test_the_app_publishes_no_docs_and_no_openapi() -> None:
    app = create_app()

    assert (app.docs_url, app.redoc_url, app.openapi_url) == (None, None, None)


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"])
def test_the_docs_and_the_openapi_paths_are_a_json_404(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 404
    assert error_of(response)["code"] == "not_found"


def test_a_trailing_slash_is_a_404_and_not_a_redirect(client: TestClient) -> None:
    response = client.get("/dummy/items/a/", follow_redirects=False)

    assert response.status_code == 404
    assert error_of(response)["code"] == "not_found"
    assert "location" not in response.headers


def test_no_cors_header_is_added(client: TestClient) -> None:
    response = client.get("/dummy/items/a", headers={"origin": "https://other.example"})
    preflight = client.options(
        "/dummy/items/a",
        headers={"origin": "https://other.example", "access-control-request-method": "GET"},
    )

    assert not [name for name in response.headers if name.startswith("access-control-")]
    assert preflight.status_code == 405
    assert not [name for name in preflight.headers if name.startswith("access-control-")]


# --- routers の口 ---


def test_a_router_is_mounted_on_the_outer_app(client: TestClient) -> None:
    response = client.get(f"/dummy/items/{SENTINEL_ID}")

    assert response.status_code == 200
    assert response.json() == {"item_id": SENTINEL_ID}


def test_every_router_is_included() -> None:
    app = create_app(
        routers=[create_dummy_router(path_prefix="/one"), create_dummy_router(path_prefix="/two")]
    )
    client = TestClient(app)

    assert client.get("/one/items/a").status_code == 200
    assert client.get("/two/items/a").status_code == 200


def test_the_outer_app_returns_the_unified_error_shape_for_every_failure(
    client: TestClient,
) -> None:
    not_found = client.get("/nope")
    method = client.post("/dummy/items/a")
    api_error = client.get("/dummy/api-error")
    teapot = client.get("/dummy/teapot")
    invalid = client.post("/dummy/items", json={"count": 0})

    assert [r.status_code for r in (not_found, method, api_error, teapot, invalid)] == [
        404,
        405,
        409,
        418,
        400,
    ]
    assert [error_of(r)["code"] for r in (not_found, method, api_error, teapot, invalid)] == [
        "not_found",
        "method_not_allowed",
        "dummy_conflict",
        "http_error",
        "invalid_request",
    ]
    assert error_of(api_error)["retryable"] is True
    assert error_of(invalid)["details"]["errors"] == [
        {"field": "name", "reason": "required"},
        {"field": "count", "reason": "range"},
    ]
    assert SENTINEL_EXCEPTION not in teapot.text


def test_an_unexpected_exception_on_the_outer_app_is_a_500_logged_once(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    response = client.get("/dummy/boom")

    assert response.status_code == 500
    assert error_of(response)["code"] == "internal_error"
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert SENTINEL_EXCEPTION not in server_side_text(caplog.records)


# --- lifespan(0003 §3) ---


def test_the_lifespan_passed_to_the_app_runs_once_at_startup_and_once_at_shutdown() -> None:
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        events.append("start")
        yield
        events.append("stop")

    app = create_app(routers=[create_dummy_router()], lifespan=lifespan)

    assert events == []
    with TestClient(app) as client:
        assert events == ["start"]
        client.get("/items/a")
        client.get("/items/b")
        assert events == ["start"]
    assert events == ["start", "stop"]


def test_the_app_works_without_a_lifespan() -> None:
    with TestClient(create_app(routers=[create_dummy_router()])) as client:
        assert client.get("/items/a").status_code == 200


def test_a_shutdown_runs_even_when_the_requests_fail() -> None:
    resource = DummyResource()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        resource.is_open = True
        try:
            yield
        finally:
            resource.is_open = False

    app = create_app(routers=[create_dummy_router()], lifespan=lifespan)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/boom").status_code == 500
        assert resource.is_open
    assert not resource.is_open
