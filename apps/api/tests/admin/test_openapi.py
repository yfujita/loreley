"""Admin API の OpenAPI(A 5.4・D 4.12(c)。C 11章 15)。

型生成(Hey API)の入力として使える内容かを確かめる: 14 操作の `operationId`・タグ・エラー応答・
`requestBody`、422 がないこと、構造(参照先がある)。期待値は B の各 EP のエラーの表から書いた。
"""

from typing import Any, NamedTuple

import pytest
from fastapi import FastAPI

from loreley_api.admin import ADMIN_API_PREFIX, create_admin_app
from loreley_api.admin import app as app_module
from loreley_api.admin.base.codes import ApiTag, DocumentTab, ErrorCode, JobStatus
from loreley_api.admin.crawler_mapping.table import TABLE, CrawlerOperation, Passthrough
from loreley_api.admin.schemas.errors import STATUS_OF_CODE, error_responses
from tests.admin.factories import make_admin_dependencies
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.fakes.inline_runner import InlineRunner
from tests.openapi_structure import iter_operations, iter_refs, structure_problems

ERROR_RESPONSE_REF = "#/components/schemas/ErrorResponse"
JSON = "application/json"
ERROR_CODE_PREFIX = "error.code: "


class ExpectedOperation(NamedTuple):
    """B の各 EP の記述から手書きした、操作ごとの期待値(実装から導かない)。"""

    operation_id: str
    method: str
    path: str
    tag: str
    # 宣言する成功のステータス(B の各 EP の「成功」)。
    ok_statuses: set[int]
    # 宣言するエラーの「ステータス → `error.code` の集合」(B 2.3 の表の EP 列と各 EP のエラー表)。
    error_codes: dict[int, set[str]]
    # 本文なし: None、あり: (スキーマ名, required)。
    request_body: tuple[str, bool] | None = None


# 400 `invalid_request` はどの EP も持つ。
INVALID_REQUEST = {400: {"invalid_request"}}
# Crawler へ中継する EP(03〜08)が、共通に返しうる失敗(B 2.3)。
CRAWLER_FAILURES = {
    502: {"crawler_error"},
    503: {"crawler_unavailable", "crawler_unreachable"},
    504: {"crawler_response_lost"},
}
STORE_UNAVAILABLE = {503: {"unavailable"}}

OPERATIONS: dict[str, ExpectedOperation] = {
    "EP-01": ExpectedOperation(
        "list_sources", "get", "/sources", "sources", {200}, INVALID_REQUEST | STORE_UNAVAILABLE
    ),
    "EP-02": ExpectedOperation(
        "get_source",
        "get",
        "/sources/{source_id}",
        "sources",
        {200},
        INVALID_REQUEST | {404: {"source_config_not_found"}} | STORE_UNAVAILABLE,
    ),
    "EP-03": ExpectedOperation(
        "register_source",
        "post",
        "/sources",
        "sources",
        {200, 201},
        {400: {"invalid_request", "config_invalid"}, 409: {"source_already_exists"}}
        | CRAWLER_FAILURES,
        ("RegisterSourceBody", True),
    ),
    "EP-04": ExpectedOperation(
        "update_source",
        "put",
        "/sources/{source_id}",
        "sources",
        {200},
        {
            400: {"invalid_request", "config_invalid"},
            404: {"source_config_not_found"},
            409: {"source_deleting"},
        }
        | CRAWLER_FAILURES,
        ("UpdateSourceBody", True),
    ),
    "EP-05": ExpectedOperation(
        "start_source_delete",
        "post",
        "/sources/{source_id}/delete-jobs",
        "sources",
        {202},
        INVALID_REQUEST
        | {404: {"source_config_not_found"}, 409: {"maintenance_enabled", "lock_held"}}
        | CRAWLER_FAILURES,
    ),
    "EP-06": ExpectedOperation(
        "start_crawl",
        "post",
        "/sources/{source_id}/crawl-jobs",
        "sources",
        {202},
        INVALID_REQUEST
        | {
            404: {"source_config_not_found"},
            409: {"source_deleting", "maintenance_enabled", "lock_held"},
        }
        | CRAWLER_FAILURES,
        ("StartCrawlBody", False),
    ),
    # ジョブに対する操作なので、タグは `jobs`(A 5.4)。
    "EP-07": ExpectedOperation(
        "cancel_job",
        "post",
        "/jobs/{job_id}/cancel",
        "jobs",
        {200, 202},
        INVALID_REQUEST
        | {404: {"job_not_found"}, 409: {"job_not_cancellable", "job_already_finished"}}
        | CRAWLER_FAILURES,
    ),
    "EP-08": ExpectedOperation(
        "release_lock",
        "delete",
        "/sources/{source_id}/lock",
        "sources",
        {200},
        INVALID_REQUEST | {409: {"lock_in_use"}} | CRAWLER_FAILURES,
    ),
    "EP-09": ExpectedOperation(
        "list_jobs", "get", "/jobs", "jobs", {200}, INVALID_REQUEST | STORE_UNAVAILABLE
    ),
    "EP-10": ExpectedOperation(
        "get_job",
        "get",
        "/jobs/{job_id}",
        "jobs",
        {200},
        INVALID_REQUEST | {404: {"job_not_found"}} | STORE_UNAVAILABLE,
    ),
    "EP-11": ExpectedOperation(
        "list_documents",
        "get",
        "/sources/{source_id}/documents",
        "documents",
        {200},
        INVALID_REQUEST | {404: {"source_config_not_found"}} | STORE_UNAVAILABLE,
    ),
    "EP-12": ExpectedOperation(
        "get_cluster",
        "get",
        "/opensearch/cluster",
        "opensearch",
        {200},
        INVALID_REQUEST | STORE_UNAVAILABLE,
    ),
    "EP-13": ExpectedOperation(
        "get_dashboard", "get", "/dashboard", "dashboard", {200}, INVALID_REQUEST
    ),
    "EP-14": ExpectedOperation("get_meta", "get", "/meta", "meta", {200}, INVALID_REQUEST),
}
ENDPOINTS = list(OPERATIONS)


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return fresh_app().openapi()


def operation_of(schema: dict[str, Any], endpoint: str) -> dict[str, Any]:
    expected = OPERATIONS[endpoint]
    return schema["paths"][expected.path][expected.method]


def statuses_of(operation: dict[str, Any], *, is_error: bool) -> set[int]:
    statuses = {int(status) for status in operation["responses"]}
    return {status for status in statuses if (status >= 400) is is_error}


def declared_codes_of(response: dict[str, Any]) -> set[str]:
    """説明文の `error.code: a, b` を、集合にする。"""
    description: str = response["description"]
    assert ERROR_CODE_PREFIX in description, description
    return set(description.split(ERROR_CODE_PREFIX, 1)[1].split(", "))


# --- 14 操作がそろう ---


def test_exactly_the_14_operations_of_ep_01_to_ep_14_are_listed(schema: dict[str, Any]) -> None:
    listed = {(method, path) for method, path, _ in iter_operations(schema)}

    assert listed == {(expected.method, expected.path) for expected in OPERATIONS.values()}
    assert len(listed) == 14


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_the_operation_id_is_the_function_name(schema: dict[str, Any], endpoint: str) -> None:
    """パスや HTTP メソッドを含まない安定した名前(生成物の名前が版で揺れない。A 5.4)。"""
    assert operation_of(schema, endpoint)["operationId"] == OPERATIONS[endpoint].operation_id


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
    assert operation_of(schema, endpoint)["tags"] == [OPERATIONS[endpoint].tag]


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
    """ステータスだけでなく、ステータスごとの `error.code` も B と一致する。"""
    operation = operation_of(schema, endpoint)
    expected = OPERATIONS[endpoint].error_codes

    assert statuses_of(operation, is_error=True) == set(expected)
    for status, codes in expected.items():
        response = operation["responses"][str(status)]
        assert response["content"][JSON]["schema"] == {"$ref": ERROR_RESPONSE_REF}
        assert declared_codes_of(response) == codes, f"{endpoint} {status}"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_the_declared_ok_statuses_are_those_of_the_endpoint_in_b(
    schema: dict[str, Any], endpoint: str
) -> None:
    """EP-03 の 200(登録済みで同じ内容)・201 と、EP-07 の 200・202 は Crawler が決める。"""
    operation = operation_of(schema, endpoint)

    assert statuses_of(operation, is_error=False) == OPERATIONS[endpoint].ok_statuses


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


def test_every_error_code_has_one_status_and_the_declaration_uses_it() -> None:
    assert set(STATUS_OF_CODE) == set(ErrorCode)
    declared = error_responses(*ErrorCode)
    assert {int(status) for status in declared} == set(STATUS_OF_CODE.values())


def fresh_app() -> FastAPI:
    deps = make_admin_dependencies(InMemoryReaders(), FixedClock(), InlineRunner())
    return create_admin_app(deps)


def declares_validation_errors(schema: dict[str, Any]) -> bool:
    return any("422" in operation["responses"] for _, _, operation in iter_operations(schema)) or (
        "HTTPValidationError" in schema["components"]["schemas"]
    )


def test_a_failed_adjustment_is_retried_and_no_unadjusted_schema_is_ever_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """調整が失敗した後の呼び出しで、FastAPI がキャッシュ済みの未調整のスキーマを返さない。

    失敗は呼び出しのたびに伝わる(調整は冪等なので、原因が直れば次の呼び出しで調整される)。
    """
    app = fresh_app()
    real_adjust = app_module._adjust_openapi
    num_calls = 0

    def fail_on_the_first_call(schema: dict[str, Any]) -> None:
        nonlocal num_calls
        num_calls += 1
        if num_calls == 1:
            raise ValueError("conflicting OpenAPI component schema: Sample")
        real_adjust(schema)

    monkeypatch.setattr(app_module, "_adjust_openapi", fail_on_the_first_call)

    with pytest.raises(ValueError, match="conflicting"):
        app.openapi()
    retried = app.openapi()

    assert not declares_validation_errors(retried)
    assert num_calls == 2


def test_a_failure_that_continues_is_raised_by_every_call(monkeypatch: pytest.MonkeyPatch) -> None:
    app = fresh_app()

    def always_fail(schema: dict[str, Any]) -> None:
        raise ValueError("conflicting OpenAPI component schema: Sample")

    monkeypatch.setattr(app_module, "_adjust_openapi", always_fail)

    for _ in range(2):
        with pytest.raises(ValueError, match="conflicting"):
            app.openapi()


def test_the_adjustment_is_applied_again_when_fastapi_regenerates_the_schema() -> None:
    """ルートの追加で FastAPI がスキーマを作り直しても、422 が復活しない。"""
    app = fresh_app()
    assert not declares_validation_errors(app.openapi())

    @app.get("/added-later")
    async def added_later(limit: int) -> dict[str, int]:  # 検証のある引数は、422 を足させる
        return {"limit": limit}

    regenerated = app.openapi()

    assert "/added-later" in regenerated["paths"]
    assert not declares_validation_errors(regenerated)


def test_the_adjustment_is_not_repeated_while_the_schema_is_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = fresh_app()
    first = app.openapi()

    monkeypatch.setattr(app_module, "_adjust_openapi", lambda schema: pytest.fail("repeated"))

    assert app.openapi() is first


# --- requestBody: 本文を依存関係で読む EP-03・04・06 だけが持つ ---


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_only_the_endpoints_that_read_a_body_declare_a_request_body(
    schema: dict[str, Any], endpoint: str
) -> None:
    operation = operation_of(schema, endpoint)
    expected = OPERATIONS[endpoint].request_body

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


@pytest.mark.parametrize("body", ["RegisterSourceBody", "UpdateSourceBody"])
@pytest.mark.parametrize(
    ("field", "title"), [("ttl_days", "Ttl Days"), ("ttl_seconds", "Ttl Seconds")]
)
def test_the_request_ttl_is_an_optional_non_null_integer(
    schema: dict[str, Any], body: str, field: str, title: str
) -> None:
    # 省略は「指定なし」、明示的な `null` は 400 `type`。型生成が null を送れる型にしないよう、
    # 任意(`required` に含まない)かつ非 null の整数にする。
    body_schema = schema["components"]["schemas"][body]

    assert body_schema["properties"][field] == {
        "title": field.replace("_", " ").title(),
        "type": "integer",
    }
    assert field not in body_schema["required"]


# --- クエリパラメータ: 実行時に検証している必須性と列挙を反映する(型生成が不正な要求を許さない) ---

ITEMS_PER_PAGE_SCHEMA = {
    "default": 25,
    "enum": [25, 50, 100],  # B 2.1
    "title": "Items Per Page",
    "type": "integer",
}
# B 5.1: 保存上の各状態と、複合の `active`(= `queued` + `running`)。
JOB_STATUS_VALUES = [
    "active",
    "queued",
    "running",
    "succeeded",
    "partially_succeeded",
    "failed",
    "cancelled",
]
# B 6.1
DOCUMENT_TAB_VALUES = ["skipped", "extract_failed", "oversize", "summary_pending"]


def query_parameters_of(schema: dict[str, Any], endpoint: str) -> dict[str, dict[str, Any]]:
    parameters = operation_of(schema, endpoint)["parameters"]
    return {parameter["name"]: parameter for parameter in parameters if parameter["in"] == "query"}


def test_the_documents_tab_is_a_required_enum_of_the_four_tabs(schema: dict[str, Any]) -> None:
    tab = query_parameters_of(schema, "EP-11")["tab"]

    assert tab["required"] is True
    assert tab["schema"] == {"enum": DOCUMENT_TAB_VALUES, "title": "Tab", "type": "string"}
    assert set(tab["schema"]["enum"]) == {tab.value for tab in DocumentTab}


@pytest.mark.parametrize("endpoint", ["EP-09", "EP-11"])
def test_items_per_page_is_an_enum_of_25_50_100_with_the_default(
    schema: dict[str, Any], endpoint: str
) -> None:
    items_per_page = query_parameters_of(schema, endpoint)["items_per_page"]

    assert items_per_page["required"] is False
    assert items_per_page["schema"] == ITEMS_PER_PAGE_SCHEMA


def test_the_jobs_status_is_an_optional_enum_of_the_states_and_active(
    schema: dict[str, Any],
) -> None:
    status = query_parameters_of(schema, "EP-09")["status"]

    assert status["required"] is False
    assert status["schema"] == {"enum": JOB_STATUS_VALUES, "title": "Status", "type": "string"}
    assert set(status["schema"]["enum"]) == {"active"} | {state.value for state in JobStatus}


def test_the_other_query_parameters_are_not_changed(schema: dict[str, Any]) -> None:
    """`sort` はタブごとに許容する項目が違うので列挙にしない。ほかも FastAPI の生成のまま。"""
    page = {
        "in": "query",
        "name": "page",
        "required": False,
        "schema": {"default": 1, "minimum": 1, "title": "Page", "type": "integer"},
    }
    nullable_string = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    jobs = query_parameters_of(schema, "EP-09")
    documents = query_parameters_of(schema, "EP-11")

    assert jobs["page"] == documents["page"] == page
    assert jobs["sort"]["schema"] == {"default": "-queued_at", "title": "Sort", "type": "string"}
    assert documents["sort"]["schema"] == {**nullable_string, "title": "Sort"}
    assert jobs["source_id"]["schema"] == {**nullable_string, "title": "Source Id"}
    assert jobs["source_id"]["required"] is False
    assert set(jobs) == {"page", "items_per_page", "sort", "source_id", "status"}
    assert set(documents) == {"tab", "page", "items_per_page", "sort"}


def test_the_enum_and_required_are_added_to_no_other_operation(schema: dict[str, Any]) -> None:
    for method, path, operation in iter_operations(schema):
        if operation["operationId"] in {"list_jobs", "list_documents"}:
            continue
        for parameter in operation.get("parameters", []):
            assert "enum" not in parameter["schema"], f"{method} {path} {parameter['name']}"
            assert parameter["required"] is (parameter["in"] == "path"), f"{method} {path}"


def test_a_rule_for_a_missing_query_parameter_fails_instead_of_being_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """操作やパラメータの名前を変えたときに、反映が外れたことに気づける。"""
    rule = app_module._QueryParameterRule("list_jobs", "renamed", ["a"])
    monkeypatch.setattr(app_module, "_QUERY_PARAMETER_RULES", (rule,))

    with pytest.raises(ValueError, match="list_jobs renamed"):
        fresh_app().openapi()


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
