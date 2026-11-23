import dataclasses

import pytest
from fastapi.testclient import TestClient

from loreley_api.admin import AdminDependencies, create_admin_app
from loreley_api.common.concurrency import BlockingRunner
from loreley_api.server import SubAppMount, create_app
from tests.api_config import make_admin_settings
from tests.fakes.clock import FixedClock


def make_dependencies() -> AdminDependencies:
    return AdminDependencies(
        settings=make_admin_settings(), clock=FixedClock(), runner=BlockingRunner()
    )


def test_the_admin_app_has_no_documentation_openapi_or_redirects() -> None:
    app = create_admin_app(make_dependencies())

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None
    assert app.router.redirect_slashes is False


def test_the_admin_app_alone_has_no_openapi_route() -> None:
    """素の `FastAPI(...)` のサブアプリは `/openapi.json` を公開するので、明示で止めている。"""
    client = TestClient(create_admin_app(make_dependencies()))

    for path in ("/openapi.json", "/docs", "/redoc"):
        assert client.get(path).status_code == 404


def test_the_unknown_path_in_the_mounted_admin_app_is_a_json_404_with_no_store() -> None:
    client = TestClient(
        create_app(mounts=[SubAppMount("/api/admin/v1", create_admin_app(make_dependencies()))])
    )

    response = client.get("/api/admin/v1/sources/SENTINEL-ID/extra")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["error"]["code"] == "not_found"
    assert "SENTINEL" not in response.text


def test_the_dependencies_are_a_frozen_bundle() -> None:
    dependencies = make_dependencies()

    with pytest.raises(dataclasses.FrozenInstanceError):
        dependencies.clock = FixedClock()  # type: ignore[misc]
