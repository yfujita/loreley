"""Admin API の OpenAPI(A 5.4・D 4.12(c)。C 11章 15)。

型生成(Hey API)の入力として使える内容かを確かめる: 14 操作の `operationId`・タグ・エラー応答・
`requestBody`、422 がないこと、構造(参照先がある)。期待値は B の各 EP のエラーの表から書いた。
"""

from typing import Any

import pytest

from loreley_api.admin import ADMIN_API_PREFIX, create_admin_app
from loreley_api.admin.base.codes import ApiTag, ErrorCode
from loreley_api.admin.crawler_mapping.table import TABLE, CrawlerOperation, Passthrough
from loreley_api.admin.schemas.errors import STATUS_OF_CODE, error_responses
from tests.admin.factories import make_admin_dependencies
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.fakes.inline_runner import InlineRunner
from tests.openapi_structure import iter_operations, iter_refs, structure_problems

ERROR_RESPONSE_REF = "#/components/schemas/ErrorResponse"
JSON = "application/json"
CRAWLER_FAILURES = {502, 503, 504}

# EP → (operationId, メソッド, パス, タグ, 宣言するエラーのステータス(B の各 EP のエラー表), 本文)。
# 本文は、なし: None、あり: (スキーマ名, required)。400 はどの EP も持つ。
OPERATIONS: dict[str, tuple[str, str, str, str, set[int], tuple[str, bool] | None]] = {
    "EP-01": ("list_sources", "get", "/sources", "sources", {400, 503}, None),
    "EP-02": ("get_source", "get", "/sources/{source_id}", "sources", {400, 404, 503}, None),
    "EP-03": (
        "register_source",
        "post",
        "/sources",
        "sources",
        {400, 409} | CRAWLER_FAILURES,
        ("RegisterSourceBody", True),
    ),
    "EP-04": (
        "update_source",
        "put",
        "/sources/{source_id}",
        "sources",
        {400, 404, 409} | CRAWLER_FAILURES,
        ("UpdateSourceBody", True),
    ),
    "EP-05": (
        "start_source_delete",
        "post",
        "/sources/{source_id}/delete-jobs",
        "sources",
        {400, 404, 409} | CRAWLER_FAILURES,
        None,
    ),
    "EP-06": (
        "start_crawl",
        "post",
        "/sources/{source_id}/crawl-jobs",
        "sources",
        {400, 404, 409} | CRAWLER_FAILURES,
        ("StartCrawlBody", False),
    ),
    # ジョブに対する操作なので、タグは `jobs`(A 5.4)。
    "EP-07": (
        "cancel_job",
        "post",
        "/jobs/{job_id}/cancel",
        "jobs",
        {400, 404, 409} | CRAWLER_FAILURES,
        None,
    ),
    "EP-08": (
        "release_lock",
        "delete",
        "/sources/{source_id}/lock",
        "sources",
        {400, 409} | CRAWLER_FAILURES,
        None,
    ),
    "EP-09": ("list_jobs", "get", "/jobs", "jobs", {400, 503}, None),
    "EP-10": ("get_job", "get", "/jobs/{job_id}", "jobs", {400, 404, 503}, None),
    "EP-11": (
        "list_documents",
        "get",
        "/sources/{source_id}/documents",
        "documents",
        {400, 404, 503},
        None,
    ),
    "EP-12": ("get_cluster", "get", "/opensearch/cluster", "opensearch", {400, 503}, None),
    "EP-13": ("get_dashboard", "get", "/dashboard", "dashboard", {400}, None),
    "EP-14": ("get_meta", "get", "/meta", "meta", {400}, None),
}
ENDPOINTS = list(OPERATIONS)


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    deps = make_admin_dependencies(InMemoryReaders(), FixedClock(), InlineRunner())
    return create_admin_app(deps).openapi()


def operation_of(schema: dict[str, Any], endpoint: str) -> dict[str, Any]:
    _, method, path, *_ = OPERATIONS[endpoint]
    return schema["paths"][path][method]


def error_statuses_of(operation: dict[str, Any]) -> set[int]:
    return {int(status) for status in operation["responses"] if int(status) >= 400}


# --- 14 操作がそろう ---


def test_exactly_the_14_operations_of_ep_01_to_ep_14_are_listed(schema: dict[str, Any]) -> None:
    listed = {(method, path) for method, path, _ in iter_operations(schema)}

    assert listed == {(method, path) for _, method, path, *_ in OPERATIONS.values()}
    assert len(listed) == 14


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_the_operation_id_is_the_function_name(schema: dict[str, Any], endpoint: str) -> None:
    """パスや HTTP メソッドを含まない安定した名前(生成物の名前が版で揺れない。A 5.4)。"""
    operation_id = OPERATIONS[endpoint][0]

    assert operation_of(schema, endpoint)["operationId"] == operation_id


def test_the_operation_ids_are_unique(schema: dict[str, Any]) -> None:
    operation_ids = [operation["operationId"] for _, _, operation in iter_operations(schema)]

    assert len(operation_ids) == len(set(operation_ids)) == 14


# --- タグ ---


def test_there_are_exactly_the_six_tags() -> None:
    assert {tag.value for tag in ApiTag} == {
        "sources",
        "jobs",
        "documents",
        "opensearch",
        "dashboard",
        "meta",
    }


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_every_operation_has_exactly_one_tag_decided_by_its_resource(
    schema: dict[str, Any], endpoint: str
) -> None:
    assert operation_of(schema, endpoint)["tags"] == [OPERATIONS[endpoint][3]]


def test_the_operations_use_only_the_six_tags(schema: dict[str, Any]) -> None:
    used = {tag for _, _, operation in iter_operations(schema) for tag in operation["tags"]}

    assert used == {tag.value for tag in ApiTag}


# --- エラー応答: 422 を宣言せず、400 などは共通のエラースキーマ ---


def test_no_operation_declares_422_and_its_schemas_are_removed(schema: dict[str, Any]) -> None:
    """基盤は検証エラーを 400 に変えるので、FastAPI が足す 422 は実際の応答と食い違う。"""
    for method, path, operation in iter_operations(schema):
        assert "422" not in operation["responses"], f"{method} {path}"
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    assert "ValidationError" not in schema["components"]["schemas"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_every_operation_declares_the_400_with_the_common_error_schema(
    schema: dict[str, Any], endpoint: str
) -> None:
    response = operation_of(schema, endpoint)["responses"]["400"]

    assert response["content"][JSON]["schema"] == {"$ref": ERROR_RESPONSE_REF}
    assert "invalid_request" in response["description"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_the_declared_errors_are_those_of_the_endpoint_in_b(
    schema: dict[str, Any], endpoint: str
) -> None:
    operation = operation_of(schema, endpoint)

    assert error_statuses_of(operation) == OPERATIONS[endpoint][4]
    for status in error_statuses_of(operation):
        content = operation["responses"][str(status)]["content"][JSON]
        assert content["schema"] == {"$ref": ERROR_RESPONSE_REF}


def test_the_error_descriptions_name_the_codes_of_b(schema: dict[str, Any]) -> None:
    descriptions = {
        endpoint: {
            status: response["description"]
            for status, response in operation_of(schema, endpoint)["responses"].items()
            if int(status) >= 400
        }
        for endpoint in ("EP-06", "EP-07", "EP-08")
    }

    assert descriptions["EP-06"]["409"].endswith("source_deleting, maintenance_enabled, lock_held")
    assert descriptions["EP-07"]["409"].endswith("job_not_cancellable, job_already_finished")
    assert descriptions["EP-08"]["409"].endswith("lock_in_use")
    assert descriptions["EP-08"]["503"].endswith("crawler_unavailable, crawler_unreachable")


def test_the_error_schema_is_the_common_format_of_a_5_2(schema: dict[str, Any]) -> None:
    components = schema["components"]["schemas"]

    assert components["ErrorResponse"]["required"] == ["error"]
    assert set(components["ErrorBody"]["required"]) == {"code", "message", "retryable"}
    assert "details" not in components["ErrorBody"]["required"]
    assert components["ErrorBody"]["properties"]["code"]["type"] == "string"
    # `details` は code ごとにキーが違うので、決めたキー以外も許す。
    assert components["ErrorDetails"]["additionalProperties"] is True
    assert {"errors", "existing_job", "lock_state", "outcome_unknown"} <= set(
        components["ErrorDetails"]["properties"]
    )


def test_the_ok_statuses_that_the_crawler_decides_are_declared(schema: dict[str, Any]) -> None:
    """EP-03 の 200(登録済みで同じ内容)と EP-07 の 202(取消要求の受付)は Crawler が決める。"""
    register = operation_of(schema, "EP-03")["responses"]
    cancel = operation_of(schema, "EP-07")["responses"]

    assert {"200", "201"} <= set(register)
    assert {"200", "202"} <= set(cancel)


def test_every_error_code_has_one_status_and_the_declaration_uses_it() -> None:
    assert set(STATUS_OF_CODE) == set(ErrorCode)
    declared = error_responses(*ErrorCode)
    assert {int(status) for status in declared} == set(STATUS_OF_CODE.values())


# --- requestBody: 本文を依存関係で読む EP-03・04・06 だけが持つ ---


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_only_the_endpoints_that_read_a_body_declare_a_request_body(
    schema: dict[str, Any], endpoint: str
) -> None:
    operation = operation_of(schema, endpoint)
    expected = OPERATIONS[endpoint][5]

    if expected is None:
        assert "requestBody" not in operation
        return
    schema_name, required = expected
    assert operation["requestBody"] == {
        "required": required,
        "content": {JSON: {"schema": {"$ref": f"#/components/schemas/{schema_name}"}}},
    }


def test_the_body_of_the_crawl_start_is_optional_and_the_others_are_required(
    schema: dict[str, Any],
) -> None:
    required = {
        endpoint: operation_of(schema, endpoint)["requestBody"]["required"]
        for endpoint in ("EP-03", "EP-04", "EP-06")
    }

    assert required == {"EP-03": True, "EP-04": True, "EP-06": False}


def test_the_request_body_schemas_are_in_the_components(schema: dict[str, Any]) -> None:
    components = schema["components"]["schemas"]

    register = components["RegisterSourceBody"]
    assert register["additionalProperties"] is False  # 未知の項目は 400(A 5.1)
    assert set(register["required"]) == {
        "source_id",
        "connector_type",
        "connector_config",
        "ratio_threshold_percent",
        "min_delete_count",
    }
    assert "source_id" not in components["UpdateSourceBody"]["properties"]
    assert components["StartCrawlBody"].get("required") is None  # 2 項目とも既定がある
    assert set(components["StartCrawlBody"]["properties"]) == {"force_delete", "rewrite_mode"}


# --- 文書の全体 ---


def test_the_servers_name_the_mount_position_because_the_paths_are_relative(
    schema: dict[str, Any],
) -> None:
    """BAPI-U-2: パスはサブアプリからの相対(`/sources`)。マウント位置は `servers` で示す。"""
    assert schema["servers"] == [{"url": ADMIN_API_PREFIX}]
    assert all(not path.startswith(ADMIN_API_PREFIX) for path in schema["paths"])


def test_the_document_info_does_not_use_the_fastapi_defaults(schema: dict[str, Any]) -> None:
    assert schema["info"] == {"title": "Loreley Admin API", "version": "v1"}


def test_the_document_is_structurally_valid_openapi_3(schema: dict[str, Any]) -> None:
    assert structure_problems(schema) == []


def test_every_component_schema_is_referenced_or_a_request_body(schema: dict[str, Any]) -> None:
    """使われない部品(取り除き損ねた 422 のスキーマなど)が残っていない。"""
    referenced = {ref.rsplit("/", 1)[-1] for ref in iter_refs(schema)}
    unused = set(schema["components"]["schemas"]) - referenced

    assert unused == set()


def test_the_structure_check_finds_the_problems_it_is_made_for(schema: dict[str, Any]) -> None:
    """検査器の自己テスト(空振りしないこと)。"""
    broken = {
        **schema,
        "paths": {
            "/x/{id}": {
                "get": {
                    "operationId": "x",
                    "responses": {"200": {"content": {JSON: {"schema": {"$ref": "#/nope"}}}}},
                },
                "post": {"operationId": "x", "responses": {}},
            }
        },
        "info": {},
    }

    problems = structure_problems(broken)

    assert any("info.title" in problem for problem in problems)
    assert any("unresolved $ref" in problem for problem in problems)
    assert any("needs a description" in problem for problem in problems)
    assert any("responses must not be empty" in problem for problem in problems)
    assert any("not declared as required" in problem for problem in problems)
    assert any("operationId is not unique" in problem for problem in problems)


# --- 宣言と実装の対応: 写像表が返しうるエラーは、すべて宣言されている ---

ENDPOINT_OF_CRAWLER_OPERATION = {
    CrawlerOperation.REGISTER_SOURCE: "EP-03",
    CrawlerOperation.UPDATE_SOURCE: "EP-04",
    CrawlerOperation.START_DELETE_JOB: "EP-05",
    CrawlerOperation.START_CRAWL: "EP-06",
    CrawlerOperation.CANCEL_JOB: "EP-07",
    CrawlerOperation.RELEASE_LOCK: "EP-08",
}


@pytest.mark.parametrize("operation", list(CrawlerOperation))
def test_every_error_the_mapping_table_returns_is_declared_with_its_code(
    schema: dict[str, Any], operation: CrawlerOperation
) -> None:
    responses = operation_of(schema, ENDPOINT_OF_CRAWLER_OPERATION[operation])["responses"]
    passthroughs = [
        outcome
        for (table_operation, _, _), outcome in TABLE.items()
        if table_operation is operation and isinstance(outcome, Passthrough)
    ]

    assert passthroughs
    for outcome in passthroughs:
        assert str(outcome.status) in responses
        assert STATUS_OF_CODE[outcome.code] == outcome.status
        assert outcome.code.value in responses[str(outcome.status)]["description"]
