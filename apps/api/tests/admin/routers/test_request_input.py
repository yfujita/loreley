"""パスの ID・クエリ・本文の検証(B 2.12。C 11章 12)。アプリ全体(`TestClient`)で確かめる。"""

import json
from typing import Annotated, Any
from urllib.parse import quote

import anyio
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from loreley_api.admin.base.codes import Reason
from loreley_api.admin.base.errors import AdminApiError, FieldViolation
from loreley_api.admin.routers.request_input import (
    JobIdPath,
    JsonObjectBody,
    PageParams,
    SourceIdPath,
    read_job_id,
    read_paging,
    reject_unknown_query,
    resolve_paging,
)
from loreley_api.common.http import install_common_http
from loreley_api.common.http.body import MAX_REQUEST_BODY_BYTES
from tests.admin.factories import SENTINEL, errors_of

PAGING = Depends(read_paging(sortable_fields={"queued_at", "status"}, default_sort="-queued_at"))


def make_client() -> TestClient:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)
    router = APIRouter()

    @router.get("/sources/{source_id}")
    async def get_source(source_id: SourceIdPath) -> dict[str, str]:
        return {"source_id": source_id}

    @router.post("/jobs/{job_id}/cancel")
    async def cancel_job(job_id: JobIdPath) -> dict[str, str]:
        return {"job_id": job_id}

    @router.get(
        "/jobs", dependencies=[Depends(reject_unknown_query({"page", "items_per_page", "sort"}))]
    )
    async def list_jobs(paging: Annotated[PageParams, PAGING]) -> dict[str, Any]:
        return {
            "page": paging.page,
            "items_per_page": paging.items_per_page,
            "sort_field": paging.sort_field,
            "descending": paging.descending,
        }

    @router.post("/echo")
    async def echo(body: JsonObjectBody) -> dict[str, Any]:
        return {"body": body}

    app.include_router(router)
    install_common_http(app)
    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    return make_client()


def assert_plain_400(response) -> None:
    """`details` なしの 400(JSON として読めない・本文が大きすぎる・Content-Type が違う)。"""
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "invalid_request",
            "message": "the request is invalid",
            "retryable": False,
        }
    }


# --- source_id ---


@pytest.mark.parametrize(
    "source_id", ["a", "A", "0", "docs-v1", "a.b_c-d", "9" * 256, "a" + "." * 255, "Z.Z"]
)
def test_a_valid_source_id_is_accepted(client: TestClient, source_id: str) -> None:
    response = client.get(f"/sources/{source_id}")

    assert response.status_code == 200
    assert response.json() == {"source_id": source_id}


@pytest.mark.parametrize(
    "source_id",
    [
        "a" * 257,
        ".a",
        "-a",
        "_a",
        "a b",
        "a!",
        "café",
        "日本語",
        "a\n",
        "a\nb",
        "a%",
        "a\x00",
        "　",
    ],
)
def test_an_invalid_source_id_is_a_format_error_without_the_value(
    client: TestClient, source_id: str
) -> None:
    response = client.get(f"/sources/{quote(source_id, safe='')}")

    assert errors_of(response) == [{"field": "source_id", "reason": "format"}]
    assert source_id.strip() not in response.text or len(source_id.strip()) <= 1


def test_a_source_id_with_an_encoded_slash_is_a_404_by_routing(client: TestClient) -> None:
    response = client.get("/sources/a%2Fb")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# --- job_id ---


@pytest.mark.parametrize(
    "job_id",
    ["j", "a b", "%", "?", "#", "日本語-ジョブ", "x" * 256, "あ" * 85, "a=b&c", "ab​c"],
)
def test_a_valid_job_id_is_accepted(client: TestClient, job_id: str) -> None:
    response = client.post(f"/jobs/{quote(job_id, safe='')}/cancel")

    assert response.status_code == 200
    assert response.json() == {"job_id": job_id}


def test_dots_only_job_ids_are_accepted_in_their_encoded_form(client: TestClient) -> None:
    """`.`・`..` は、URL の正規化で崩れないよう `%2E` で送る(Crawler に渡すときも同じ)。"""
    for encoded, expected in (("%2E", "."), ("%2E%2E", "..")):
        response = client.post(f"/jobs/{encoded}/cancel")

        assert response.json() == {"job_id": expected}


@pytest.mark.parametrize(
    "job_id",
    ["x" * 257, "あ" * 86, "a\x01b", "a\tb", "a\nb", "\x7f", "a\x00", "\x1f", "\u0085"],
)
def test_an_invalid_job_id_is_a_format_error_without_the_value(
    client: TestClient, job_id: str
) -> None:
    response = client.post(f"/jobs/{quote(job_id, safe='')}/cancel")

    assert errors_of(response) == [{"field": "job_id", "reason": "format"}]


def test_a_job_id_with_a_lone_surrogate_is_a_format_error() -> None:
    """URL では表せないので、依存関係を直接呼ぶ。"""
    with pytest.raises(AdminApiError) as error_info:
        anyio.run(read_job_id, "a\ud800b")

    assert error_info.value.details == {"errors": [{"field": "job_id", "reason": "format"}]}


def test_an_empty_job_id_is_a_404_by_routing(client: TestClient) -> None:
    assert client.post("/jobs//cancel").status_code == 404


# --- 未知のクエリ ---


def test_an_unknown_query_is_an_unknown_field_error(client: TestClient) -> None:
    response = client.get("/jobs", params={"page": "1", "SENTINEL_NAME": SENTINEL})

    assert errors_of(response) == [{"field": "SENTINEL_NAME", "reason": "unknown_field"}]
    assert SENTINEL not in response.text  # 値は載せない


def test_every_unknown_query_is_reported_in_a_stable_order(client: TestClient) -> None:
    response = client.get("/jobs?zeta=1&alpha=2&page=1")

    assert errors_of(response) == [
        {"field": "alpha", "reason": "unknown_field"},
        {"field": "zeta", "reason": "unknown_field"},
    ]


def test_an_unknown_query_name_is_escaped_and_truncated(client: TestClient) -> None:
    response = client.get(f"/jobs?%0Aevil{'x' * 300}=1")

    [error] = errors_of(response)
    assert error["reason"] == "unknown_field"
    assert error["field"].startswith("\\nevil")
    assert "\n" not in error["field"]
    assert len(error["field"]) == 100


def test_the_defined_queries_are_accepted(client: TestClient) -> None:
    response = client.get("/jobs?page=2&items_per_page=50&sort=status")

    assert response.status_code == 200


# --- ページング ---


def test_the_paging_defaults(client: TestClient) -> None:
    response = client.get("/jobs")

    assert response.json() == {
        "page": 1,
        "items_per_page": 25,
        "sort_field": "queued_at",
        "descending": True,
    }


@pytest.mark.parametrize(
    ("sort", "sort_field", "descending"),
    [("status", "status", False), ("-status", "status", True), ("queued_at", "queued_at", False)],
)
def test_the_sort_has_a_field_and_a_direction(
    client: TestClient, sort: str, sort_field: str, descending: bool
) -> None:
    body = client.get("/jobs", params={"sort": sort}).json()

    assert (body["sort_field"], body["descending"]) == (sort_field, descending)


@pytest.mark.parametrize("sort", ["bogus", "-bogus", "--status", "", "status,queued_at", "-"])
def test_an_unsupported_sort_is_an_unsupported_error(client: TestClient, sort: str) -> None:
    response = client.get("/jobs", params={"sort": sort})

    assert errors_of(response) == [{"field": "sort", "reason": "unsupported"}]


@pytest.mark.parametrize("items_per_page", ["25", "50", "100"])
def test_the_items_per_page_choices_are_accepted(client: TestClient, items_per_page: str) -> None:
    response = client.get("/jobs", params={"items_per_page": items_per_page})

    assert response.json()["items_per_page"] == int(items_per_page)


@pytest.mark.parametrize("items_per_page", ["0", "10", "26", "101", "1000", "-25"])
def test_an_items_per_page_outside_the_choices_is_unsupported(
    client: TestClient, items_per_page: str
) -> None:
    response = client.get("/jobs", params={"items_per_page": items_per_page})

    assert errors_of(response) == [{"field": "items_per_page", "reason": "unsupported"}]


@pytest.mark.parametrize("page", ["0", "-1"])
def test_a_page_below_one_is_a_range_error(client: TestClient, page: str) -> None:
    response = client.get("/jobs", params={"page": page})

    assert errors_of(response) == [{"field": "page", "reason": "range"}]


@pytest.mark.parametrize("name", ["page", "items_per_page"])
@pytest.mark.parametrize("value", ["abc", "1.5", "SENTINEL-NUMBER", ""])
def test_a_non_integer_is_a_type_error_without_the_value(
    client: TestClient, name: str, value: str
) -> None:
    response = client.get("/jobs", params={name: value})

    assert errors_of(response) == [{"field": name, "reason": "type"}]
    assert "SENTINEL" not in response.text


@pytest.mark.parametrize(
    ("page", "items_per_page"), [(400, 25), (200, 50), (100, 100), (1, 100), (399, 25)]
)
def test_a_window_up_to_10000_is_accepted(
    client: TestClient, page: int, items_per_page: int
) -> None:
    response = client.get("/jobs", params={"page": page, "items_per_page": items_per_page})

    assert response.status_code == 200
    assert page * items_per_page <= 10_000


@pytest.mark.parametrize(
    ("page", "items_per_page"), [(401, 25), (201, 50), (101, 100), (10**12, 25)]
)
def test_a_window_over_10000_is_a_range_error_on_page(
    client: TestClient, page: int, items_per_page: int
) -> None:
    response = client.get("/jobs", params={"page": page, "items_per_page": items_per_page})

    assert errors_of(response) == [{"field": "page", "reason": "range"}]


def test_resolve_paging_returns_the_params_for_a_valid_request() -> None:
    resolved = resolve_paging(3, 50, "-indexed_at", sortable_fields={"indexed_at"})

    assert resolved == PageParams(3, 50, "indexed_at", descending=True)


def test_resolve_paging_returns_every_violation_in_a_stable_order() -> None:
    resolved = resolve_paging(1, 7, "bogus", sortable_fields={"indexed_at"})

    assert resolved == [
        FieldViolation("items_per_page", Reason.UNSUPPORTED),
        FieldViolation("sort", Reason.UNSUPPORTED),
    ]


def test_resolve_paging_does_not_judge_the_window_when_the_page_size_is_unsupported() -> None:
    resolved = resolve_paging(10**9, 7, "x", sortable_fields={"x"})

    assert resolved == [FieldViolation("items_per_page", Reason.UNSUPPORTED)]


def test_several_paging_violations_are_all_reported(client: TestClient) -> None:
    response = client.get("/jobs", params={"items_per_page": "7", "sort": "bogus"})

    assert errors_of(response) == [
        {"field": "items_per_page", "reason": "unsupported"},
        {"field": "sort", "reason": "unsupported"},
    ]


# --- 本文 ---


@pytest.mark.parametrize(
    "headers",
    [{}, {"content-type": "application/json"}, {"content-type": "text/plain"}],
)
def test_an_empty_body_is_an_empty_object_whatever_the_content_type(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.post("/echo", headers=headers)

    assert response.json() == {"body": {}}


def test_a_zero_content_length_is_an_empty_object(client: TestClient) -> None:
    response = client.post("/echo", content=b"", headers={"content-type": "application/xml"})

    assert response.json() == {"body": {}}


@pytest.mark.parametrize(
    "content_type",
    [
        "application/json",
        "application/json; charset=utf-8",
        "APPLICATION/JSON",
        " application/json ;charset=UTF-8",
    ],
)
def test_a_json_object_is_read(client: TestClient, content_type: str) -> None:
    body = {"a": 1, "nested": {"b": [1, 2, None]}, "text": "日本語"}

    response = client.post(
        "/echo",
        content=json.dumps(body, ensure_ascii=False).encode(),
        headers={"content-type": content_type},
    )

    assert response.json() == {"body": body}


def test_an_empty_json_object_is_read(client: TestClient) -> None:
    response = client.post("/echo", json={})

    assert response.json() == {"body": {}}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"content-type": "text/plain"},
        {"content-type": "application/jsonx"},
        {"content-type": ""},
    ],
)
def test_a_body_with_another_content_type_is_a_plain_400(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.post("/echo", content=b'{"a": 1}', headers=headers)

    assert_plain_400(response)


@pytest.mark.parametrize(
    "content",
    [
        b"{",
        b'{"a": }',
        b"   ",
        b"\xff\xfe{}",
        b'{"a": NaN}',
        b'{"a": Infinity}',
        b'{"a": -Infinity}',
        b"[" * 100_000,
        f'{{"a": "{SENTINEL}"'.encode(),
    ],
)
def test_a_body_that_is_not_json_is_a_plain_400(client: TestClient, content: bytes) -> None:
    response = client.post("/echo", content=content, headers={"content-type": "application/json"})

    assert_plain_400(response)
    assert SENTINEL not in response.text


@pytest.mark.parametrize("content", [b"[]", b'[{"a": 1}]', b'"text"', b"123", b"true", b"null"])
def test_a_json_value_that_is_not_an_object_is_a_body_type_error(
    client: TestClient, content: bytes
) -> None:
    response = client.post("/echo", content=content, headers={"content-type": "application/json"})

    assert errors_of(response) == [{"field": "body", "reason": "type"}]


def test_a_body_over_1_mib_is_a_plain_400(client: TestClient) -> None:
    padding = "x" * MAX_REQUEST_BODY_BYTES
    content = json.dumps({"a": padding}).encode()

    response = client.post("/echo", content=content, headers={"content-type": "application/json"})

    assert_plain_400(response)


def test_a_body_exactly_at_1_mib_is_read(client: TestClient) -> None:
    overhead = len(json.dumps({"a": ""}).encode())
    content = json.dumps({"a": "x" * (MAX_REQUEST_BODY_BYTES - overhead)}).encode()
    assert len(content) == MAX_REQUEST_BODY_BYTES

    response = client.post("/echo", content=content, headers={"content-type": "application/json"})

    assert response.status_code == 200
