import logging

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from loreley_api.common.http import install_common_http
from loreley_api.common.http.middleware import UNMATCHED_ROUTE
from tests.log_records import record_text, server_side_text

SENTINEL_ID = "SENTINEL-ITEM-ID"
SENTINEL_QUERY = "SENTINEL-QUERY"
SENTINEL_EXCEPTION = "SENTINEL-EXCEPTION-MESSAGE"
ACCESS_LOGGER = "loreley_api.access"


def make_app() -> FastAPI:
    app = FastAPI(redirect_slashes=False)
    router = APIRouter()

    @router.get("/items/{item_id}")
    async def get_item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    @router.get("/quiet")
    async def quiet() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/api/things/{thing_id}")
    async def get_thing(thing_id: str) -> dict[str, str]:
        return {"thing_id": thing_id}

    @router.get("/api/boom")
    async def boom() -> None:
        raise RuntimeError(SENTINEL_EXCEPTION)

    app.include_router(router)
    install_common_http(app, debug_access_log_paths={"/quiet"})
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(make_app(), raise_server_exceptions=True)


@pytest.fixture
def logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG)
    return caplog


def access_records(logs: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in logs.records if record.name == ACCESS_LOGGER]


def test_the_access_log_has_only_the_method_the_route_template_the_status_and_the_time(
    client: TestClient, logs: pytest.LogCaptureFixture
) -> None:
    client.get(f"/items/{SENTINEL_ID}", params={"q": SENTINEL_QUERY}, headers={"x-h": "SENTINEL"})

    (record,) = access_records(logs)
    method, template, status, elapsed = record.getMessage().split(" ")
    assert (method, template, status) == ("GET", "/items/{item_id}", "200")
    assert elapsed.endswith("ms")
    assert float(elapsed.removesuffix("ms")) >= 0
    assert record.levelno == logging.INFO
    assert "SENTINEL" not in record_text(record)


def test_a_request_that_matches_no_route_logs_a_dash_instead_of_the_path(
    client: TestClient, logs: pytest.LogCaptureFixture
) -> None:
    client.get(f"/SENTINEL-PATH/{SENTINEL_ID}")

    (record,) = access_records(logs)
    assert record.getMessage().startswith(f"GET {UNMATCHED_ROUTE} 404 ")
    assert "SENTINEL" not in record_text(record)


def test_the_status_of_an_error_response_is_logged(
    client: TestClient, logs: pytest.LogCaptureFixture
) -> None:
    client.post("/items/x")

    (record,) = access_records(logs)
    assert record.getMessage().startswith("POST /items/{item_id} 405 ")


def test_a_debug_access_log_path_is_logged_at_debug_and_the_others_at_info(
    client: TestClient, logs: pytest.LogCaptureFixture
) -> None:
    client.get("/quiet")
    client.get("/items/a")

    levels = {record.getMessage().split(" ")[1]: record.levelno for record in access_records(logs)}
    assert levels == {"/quiet": logging.DEBUG, "/items/{item_id}": logging.INFO}


def test_each_request_is_logged_once(client: TestClient, logs: pytest.LogCaptureFixture) -> None:
    for path in ("/items/a", "/quiet", "/nope", "/api/things/a"):
        client.get(path)

    assert len(access_records(logs)) == 4


# --- Cache-Control: no-store ---


@pytest.mark.parametrize("path", ["/api/things/a", "/api/nope", "/api/", "/api/x/y/z"])
def test_a_response_under_api_has_no_store_even_for_a_404(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/items/a", "/quiet", "/healthz", "/nope", "/api", "/apix/a"])
def test_a_response_outside_api_has_no_cache_control(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert "cache-control" not in response.headers


# --- 想定外の例外 ---


def test_an_unexpected_exception_becomes_a_500_and_is_not_raised_again(
    client: TestClient, logs: pytest.LogCaptureFixture
) -> None:
    """`raise_server_exceptions=True` でも、テストのクライアントまで例外が上がらない。"""
    response = client.get("/api/boom")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "an internal error occurred",
            "retryable": False,
        }
    }
    assert response.headers["cache-control"] == "no-store"
    assert SENTINEL_EXCEPTION not in response.text


def test_an_unexpected_exception_is_logged_once_by_class_name_and_origin_only(
    client: TestClient, logs: pytest.LogCaptureFixture
) -> None:
    client.get("/api/boom")

    errors = [record for record in logs.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert (
        errors[0].getMessage().startswith("request failed unexpectedly: error=RuntimeError origin=")
    )
    assert errors[0].exc_info is None
    assert not errors[0].exc_text
    assert errors[0].stack_info is None
    assert SENTINEL_EXCEPTION not in server_side_text(logs.records)
    (access,) = access_records(logs)
    assert access.getMessage().startswith("GET /api/boom 500 ")


def test_the_app_keeps_serving_after_an_unexpected_exception(client: TestClient) -> None:
    client.get("/api/boom")

    assert client.get("/items/a").status_code == 200
