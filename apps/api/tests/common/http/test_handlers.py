"""例外から統一エラー形式への変換(A 5.2)。最小の FastAPI に設置して確かめる。"""

from typing import Literal

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field

from loreley_api.common.http import ApiError, install_common_http
from loreley_api.common.http.handlers import (
    MAX_FIELD_NAME_CHARS,
    field_name_of,
    format_field_name_part,
    reason_of,
)

SENTINEL = "SENTINEL-INPUT-VALUE"


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    count: int = Field(1, ge=1, le=10)
    tags: list[str] = Field(default_factory=list, max_length=2)
    kind: Literal["a", "b"] = "a"
    code: str = Field("abc", pattern="^[a-z]+$")
    step: int = Field(5, multiple_of=5)


def make_app() -> FastAPI:
    app = FastAPI(redirect_slashes=False)

    @app.post("/items")
    async def create_item(item: Item) -> dict[str, str]:
        return {"name": item.name}

    @app.get("/numbers/{number}")
    async def get_number(number: int, limit: int = 1) -> dict[str, int]:
        return {"number": number, "limit": limit}

    @app.get("/teapot")
    async def teapot() -> None:
        raise HTTPException(418, detail=SENTINEL)

    @app.get("/api-error")
    async def api_error() -> None:
        raise ApiError(
            409,
            "lock_in_use",
            "the lock is in use",
            retryable=True,
            details={"outcome_unknown": True},
        )

    @app.get("/only-get")
    async def only_get(request: Request) -> dict[str, str]:
        return {"method": request.method}

    install_common_http(app)
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(make_app(), raise_server_exceptions=False)


def error_of(response) -> dict:
    return response.json()["error"]


def test_an_undefined_path_is_a_404_not_found(client: TestClient) -> None:
    response = client.get("/SENTINEL-PATH")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "the path is not defined",
            "retryable": False,
        }
    }
    assert "SENTINEL-PATH" not in response.text


def test_an_undefined_method_is_a_405_with_the_allow_header(client: TestClient) -> None:
    response = client.post("/only-get")

    assert response.status_code == 405
    assert error_of(response)["code"] == "method_not_allowed"
    assert response.headers["allow"] == "GET"


def test_another_http_exception_keeps_its_status_and_hides_its_detail(client: TestClient) -> None:
    response = client.get("/teapot")

    assert response.status_code == 418
    assert error_of(response) == {
        "code": "http_error",
        "message": "the request cannot be handled",
        "retryable": False,
    }
    assert SENTINEL not in response.text


def test_an_api_error_is_returned_as_given(client: TestClient) -> None:
    response = client.get("/api-error")

    assert response.status_code == 409
    assert error_of(response) == {
        "code": "lock_in_use",
        "message": "the lock is in use",
        "retryable": True,
        "details": {"outcome_unknown": True},
    }


@pytest.mark.parametrize(
    ("body", "field", "reason"),
    [
        ({}, "name", "required"),
        ({"name": "a", "zzz": 1}, "zzz", "unknown_field"),
        ({"name": 1}, "name", "type"),
        ({"name": "a", "count": "x"}, "count", "type"),
        ({"name": "a", "count": 0}, "count", "range"),
        ({"name": "a", "count": 11}, "count", "range"),
        ({"name": "a", "tags": [1]}, "tags[0]", "type"),
        ({"name": "a", "tags": ["a", "b", "c"]}, "tags", "range"),
        ({"name": "a", "kind": "c"}, "kind", "unsupported"),
        ({"name": "a", "code": "ABC"}, "code", "format"),
        ({"name": "a", "step": 3}, "step", "range"),
        ([], "body", "type"),
    ],
)
def test_a_validation_error_becomes_a_400_with_the_field_and_the_reason(
    client: TestClient, body: object, field: str, reason: str
) -> None:
    response = client.post("/items", json=body)

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "invalid_request",
            "message": "the request is invalid",
            "retryable": False,
            "details": {"errors": [{"field": field, "reason": reason}]},
        }
    }


def test_a_missing_body_is_reported_as_the_body_being_required(client: TestClient) -> None:
    response = client.post("/items")

    assert response.status_code == 400
    assert error_of(response)["details"] == {"errors": [{"field": "body", "reason": "required"}]}


def test_query_and_path_errors_have_no_location_prefix(client: TestClient) -> None:
    response = client.get("/numbers/SENTINEL-PATH-VALUE", params={"limit": "SENTINEL-QUERY-VALUE"})

    assert response.status_code == 400
    assert error_of(response)["details"]["errors"] == [
        {"field": "number", "reason": "type"},
        {"field": "limit", "reason": "type"},
    ]
    assert "SENTINEL" not in response.text


def test_every_violation_is_reported(client: TestClient) -> None:
    response = client.post("/items", json={"count": 0, "zzz": 1})

    fields = {item["field"]: item["reason"] for item in error_of(response)["details"]["errors"]}
    assert fields == {"name": "required", "count": "range", "zzz": "unknown_field"}


def test_a_body_that_is_not_json_is_a_400_without_details(client: TestClient) -> None:
    response = client.post(
        "/items", content=b"{SENTINEL", headers={"content-type": "application/json"}
    )

    assert response.status_code == 400
    assert error_of(response) == {
        "code": "invalid_request",
        "message": "the request is invalid",
        "retryable": False,
    }
    assert "SENTINEL" not in response.text


@pytest.mark.parametrize(
    "body",
    [
        {"name": {"nested": SENTINEL}},
        {"name": "a", "count": SENTINEL},
        {"name": "a", "tags": [SENTINEL, 1]},
        {"name": "a", "kind": SENTINEL},
        {"name": "a", "code": SENTINEL.upper()},
    ],
)
def test_no_input_value_appears_in_the_response(client: TestClient, body: object) -> None:
    response = client.post("/items", json=body)

    assert response.status_code == 400
    assert SENTINEL not in response.text
    assert SENTINEL.upper() not in response.text
    assert set(error_of(response)["details"]["errors"][0]) == {"field", "reason"}


# --- reason の写像 ---


@pytest.mark.parametrize(
    ("pydantic_type", "reason"),
    [
        ("missing", "required"),
        ("extra_forbidden", "unknown_field"),
        ("string_type", "type"),
        ("int_type", "type"),
        ("int_parsing", "type"),
        ("float_parsing", "type"),
        ("greater_than", "range"),
        ("greater_than_equal", "range"),
        ("less_than", "range"),
        ("less_than_equal", "range"),
        ("too_short", "range"),
        ("too_long", "range"),
        ("multiple_of", "range"),
        ("literal_error", "unsupported"),
        ("enum", "unsupported"),
        ("string_pattern_mismatch", "format"),
        ("value_error", "format"),
        ("something_new", "format"),
    ],
)
def test_the_reason_of_a_pydantic_error_type(pydantic_type: str, reason: str) -> None:
    assert reason_of(pydantic_type) == reason


# --- 項目名 ---


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        (("body", "name"), "name"),
        (("body", "items", 0, "name"), "items[0].name"),
        (("body", "matrix", 1, 2), "matrix[1][2]"),
        (("query", "limit"), "limit"),
        (("path", "source_id"), "source_id"),
        (("header", "x-token"), "x-token"),
        (("cookie", "session"), "session"),
        (("body",), "body"),
        (("query",), "query"),
        (("name",), "name"),
        ((), "request"),
    ],
)
def test_the_field_name_is_dotted_with_indexes_and_without_the_location(
    location: tuple, expected: str
) -> None:
    assert field_name_of(location) == expected


def test_a_field_name_that_comes_from_the_input_is_sanitized() -> None:
    assert format_field_name_part("a\nb\tc\x00d") == "a\\nb\\tc\\x00d"
    assert format_field_name_part("a\ud800b") == "a�b"
    assert format_field_name_part("x" * 150) == "x" * MAX_FIELD_NAME_CHARS


def test_truncation_does_not_cut_an_escape_sequence() -> None:
    value = "x" * (MAX_FIELD_NAME_CHARS - 1) + "\n"

    assert format_field_name_part(value) == "x" * (MAX_FIELD_NAME_CHARS - 1)


def test_an_unknown_field_name_in_the_body_is_sanitized_in_the_response(
    client: TestClient,
) -> None:
    body = b'{"name": "a", "line1\\nline2": 1, "' + b"k" * 150 + b'": 1}'

    response = client.post("/items", content=body, headers={"content-type": "application/json"})

    assert response.status_code == 400
    fields = [item["field"] for item in error_of(response)["details"]["errors"]]
    assert fields == ["line1\\nline2", "k" * MAX_FIELD_NAME_CHARS]


def test_a_lone_surrogate_in_a_field_name_is_a_format_error_on_the_body(
    client: TestClient,
) -> None:
    """pydantic は、孤立サロゲートを含む項目名を、本文全体の違反にする(応答に入力を出さない)。"""
    body = b'{"name": "a", "lone\\ud800": 1}'

    response = client.post("/items", content=body, headers={"content-type": "application/json"})

    assert response.status_code == 400
    assert error_of(response)["details"] == {"errors": [{"field": "body", "reason": "format"}]}
