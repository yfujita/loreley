"""共通のエラー形式(crawler-api 3.3)と、例外から HTTP 応答への写像。"""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from loreley_crawler.api.errors import register_error_handlers
from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.jobs import JobStatus
from tests.api.support import SOURCE_ID, ApiEnv, new_source_body, update_body
from tests.fakes.in_memory_repository import CREATE, FETCH
from tests.jobs.support import JOB_ID

SENTINEL = "SENTINEL-exception-message"


def assert_error_shape(response, status_code: int, code: str, *, retryable: bool = False) -> None:
    assert response.status_code == status_code, response.text
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert {"code", "message", "retryable"} <= set(error)
    assert set(error) <= {"code", "message", "retryable", "details"}
    assert (error["code"], error["retryable"]) == (code, retryable)
    assert isinstance(error["message"], str) and error["message"]


# --- 共通の HTTP エラー ---


def test_an_undefined_path_is_404_not_found(api: ApiEnv) -> None:
    assert_error_shape(api.client.get("/nope"), 404, "not_found")
    assert_error_shape(api.client.post("/sources/a/b/c"), 404, "not_found")


def test_an_undefined_method_is_405_method_not_allowed(api: ApiEnv) -> None:
    assert_error_shape(api.client.get("/sources"), 405, "method_not_allowed")
    assert_error_shape(api.client.patch(f"/sources/{SOURCE_ID}"), 405, "method_not_allowed")
    assert_error_shape(api.client.get(f"/jobs/{JOB_ID}/cancel"), 405, "method_not_allowed")


def test_every_error_message_is_a_fixed_sentence(api: ApiEnv) -> None:
    api.jobs.seed_source()
    cases = [
        api.client.get("/nope"),
        api.post(f"/sources/{SOURCE_ID}/crawl-jobs", {"x": SENTINEL}),
        api.post("/jobs/job-unknown/cancel"),
        api.post("/sources", raw=SENTINEL.encode()),
    ]

    for response in cases:
        assert SENTINEL not in response.text


# --- 503・500(全エンドポイント) ---

ENDPOINTS = [
    pytest.param("post", f"/sources/{SOURCE_ID}/crawl-jobs", None, "sources", FETCH, id="crawl"),
    pytest.param("post", f"/sources/{SOURCE_ID}/delete-jobs", None, "sources", FETCH, id="delete"),
    pytest.param("post", f"/jobs/{JOB_ID}/cancel", None, "jobs", FETCH, id="cancel"),
    pytest.param("delete", f"/sources/{SOURCE_ID}/lock", None, "jobs", FETCH, id="lock"),
    pytest.param("post", "/sources", new_source_body(), "sources", CREATE, id="register"),
    pytest.param("put", f"/sources/{SOURCE_ID}", update_body(), "sources", FETCH, id="update"),
]


def call(api: ApiEnv, method: str, path: str, body: dict | None):
    if method == "post":
        return api.post(path, body)
    if method == "put":
        return api.put(path, body)
    return api.client.delete(path)


def repository_of(api: ApiEnv, name: str):
    return api.sources_repository if name == "sources" else api.jobs.jobs_repository


@pytest.mark.parametrize(("method", "path", "body", "repository", "operation"), ENDPOINTS)
def test_a_store_outage_is_503_unavailable_and_retryable(
    api: ApiEnv, caplog: pytest.LogCaptureFixture, method, path, body, repository, operation
) -> None:
    api.jobs.seed_source()
    api.jobs.seed_job(JOB_ID, status=JobStatus.QUEUED)
    repository_of(api, repository).behavior.inject(
        operation, StoreUnavailableError("opensearch_unavailable"), times=None
    )

    with caplog.at_level(logging.DEBUG):
        response = call(api, method, path, body)

    assert_error_shape(response, 503, "unavailable", retryable=True)
    assert "opensearch_unavailable" in caplog.text  # 固定の理由名だけを残す


@pytest.mark.parametrize(("method", "path", "body", "repository", "operation"), ENDPOINTS)
def test_an_unexpected_store_response_is_500_internal_error_without_the_error_type(
    api: ApiEnv, caplog: pytest.LogCaptureFixture, method, path, body, repository, operation
) -> None:
    api.jobs.seed_source()
    api.jobs.seed_job(JOB_ID, status=JobStatus.QUEUED)
    repository_of(api, repository).behavior.inject(
        operation, StoreUnexpectedResponseError("mapper_parsing_exception"), times=None
    )

    with caplog.at_level(logging.DEBUG):
        response = call(api, method, path, body)

    assert_error_shape(response, 500, "internal_error")
    assert "mapper_parsing_exception" not in response.text
    assert "error_type=mapper_parsing_exception" in caplog.text


@pytest.mark.parametrize(("method", "path", "body", "repository", "operation"), ENDPOINTS)
def test_an_unexpected_exception_is_500_internal_error_and_its_message_is_not_exposed(
    api: ApiEnv, caplog: pytest.LogCaptureFixture, method, path, body, repository, operation
) -> None:
    api.jobs.seed_source()
    api.jobs.seed_job(JOB_ID, status=JobStatus.QUEUED)
    repository_of(api, repository).behavior.inject(operation, RuntimeError(SENTINEL), times=None)

    with caplog.at_level(logging.DEBUG):
        response = call(api, method, path, body)

    assert_error_shape(response, 500, "internal_error")
    assert SENTINEL not in response.text
    assert SENTINEL not in caplog.text
    assert "RuntimeError" in caplog.text


def test_a_transient_store_failure_is_retried_and_the_request_succeeds(api: ApiEnv) -> None:
    api.jobs.seed_source()
    api.sources_repository.behavior.inject(FETCH, StoreUnavailableError("blip"), times=1)

    response = api.post(f"/sources/{SOURCE_ID}/crawl-jobs")

    assert response.status_code == 202


# --- pydantic の検証エラー(位置と型だけにする) ---


class _StrictBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    count: int
    name: str


def test_a_pydantic_validation_error_is_400_with_locations_and_types_only() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/probe")
    def probe(body: _StrictBody) -> dict[str, str]:
        return {"ok": "yes"}

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/probe", json={"count": SENTINEL, "extra": SENTINEL})

    assert_error_shape(response, 400, "invalid_request")
    assert SENTINEL not in response.text
    assert response.json()["error"]["details"]["errors"] == [
        {"field": "body.count", "reason": "type"},
        {"field": "body.name", "reason": "required"},
        {"field": "body.extra", "reason": "unknown_field"},
    ]


# --- 本文の完全一致(`details` の不在・固定文) ---


@pytest.mark.parametrize(
    ("make_failure", "status_code", "code", "message", "retryable"),
    [
        (
            lambda: RuntimeError(SENTINEL),
            500,
            "internal_error",
            "an internal error occurred",
            False,
        ),
        (
            lambda: StoreUnexpectedResponseError("x"),
            500,
            "internal_error",
            "an internal error occurred",
            False,
        ),
        (
            lambda: StoreUnavailableError("x"),
            503,
            "unavailable",
            "the service is temporarily unavailable",
            True,
        ),
    ],
    ids=["unexpected-exception", "unexpected-store-response", "store-unavailable"],
)
def test_the_failure_bodies_are_exactly_the_fixed_form_without_details(
    api: ApiEnv, make_failure, status_code: int, code: str, message: str, retryable: bool
) -> None:
    api.jobs.seed_source()
    api.sources_repository.behavior.inject(FETCH, make_failure(), times=None)

    response = api.post(f"/sources/{SOURCE_ID}/crawl-jobs")

    assert response.status_code == status_code
    assert response.json() == {"error": {"code": code, "message": message, "retryable": retryable}}


def test_the_404_and_405_bodies_are_exactly_the_fixed_form_without_details(api: ApiEnv) -> None:
    fixed = "the request cannot be handled"

    assert api.client.get("/nope").json() == {
        "error": {"code": "not_found", "message": fixed, "retryable": False}
    }
    assert api.client.get("/sources").json() == {
        "error": {"code": "method_not_allowed", "message": fixed, "retryable": False}
    }
