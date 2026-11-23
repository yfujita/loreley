import inspect
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from loreley_api.health import HEALTH_PATH, create_health_router
from loreley_api.server import create_app


def test_the_health_check_works_on_a_plain_fastapi_app() -> None:
    """`server` に依存しない独立した機能パッケージ(素の FastAPI に載せても動く)。"""
    app = FastAPI()
    app.include_router(create_health_router())

    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_path_is_healthz() -> None:
    assert HEALTH_PATH == "/healthz"


def test_the_route_function_is_async_so_that_no_thread_is_used() -> None:
    (route,) = create_health_router().routes

    assert inspect.iscoroutinefunction(route.endpoint)


def test_the_app_has_no_healthz_unless_the_router_is_passed() -> None:
    without = TestClient(create_app())
    with_router = TestClient(create_app(routers=[create_health_router()]))

    assert without.get("/healthz").status_code == 404
    assert with_router.get("/healthz").status_code == 200


def test_the_response_has_no_cache_control() -> None:
    client = TestClient(create_app(routers=[create_health_router()]))

    assert "cache-control" not in client.get("/healthz").headers


def test_only_get_is_defined() -> None:
    client = TestClient(create_app(routers=[create_health_router()]))

    response = client.post("/healthz")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert response.headers["allow"] == "GET"


def test_a_trailing_slash_is_a_404_and_not_a_redirect() -> None:
    client = TestClient(create_app(routers=[create_health_router()]))

    response = client.get("/healthz/", follow_redirects=False)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_the_access_log_of_the_health_check_is_debug_and_others_are_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    client = TestClient(
        create_app(routers=[create_health_router()], debug_access_log_paths={HEALTH_PATH})
    )

    client.get("/healthz")
    client.get("/nope")

    levels = [
        (record.getMessage().split(" ")[:3], record.levelno)
        for record in caplog.records
        if record.name == "loreley_api.access"
    ]
    assert levels == [
        (["GET", "/healthz", "200"], logging.DEBUG),
        (["GET", "-", "404"], logging.INFO),
    ]
