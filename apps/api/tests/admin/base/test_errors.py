import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from loreley_api.admin.base.codes import (
    ComponentState,
    ErrorCode,
    LockState,
    Reason,
    UnavailableReason,
)
from loreley_api.admin.base.errors import (
    AdminApiError,
    FieldViolation,
    config_invalid,
    crawler_error,
    crawler_response_lost,
    crawler_unreachable,
    invalid_request,
    job_not_found,
    source_config_not_found,
    unavailable,
)
from loreley_api.common.http import ApiError, install_common_http


def test_the_codes_are_the_ones_in_the_specification() -> None:
    """B 2.3 の Admin 固有の code と、Admin API が直接返す共通 code。"""
    assert {code.value for code in ErrorCode} == {
        "invalid_request",
        "unavailable",
        "config_invalid",
        "source_config_not_found",
        "job_not_found",
        "lock_held",
        "lock_in_use",
        "source_deleting",
        "maintenance_enabled",
        "source_already_exists",
        "job_not_cancellable",
        "job_already_finished",
        "crawler_error",
        "crawler_unavailable",
        "crawler_unreachable",
        "crawler_response_lost",
    }


def test_the_reasons_and_state_values_are_the_ones_in_the_specification() -> None:
    assert {reason.value for reason in Reason} == {
        "required",
        "type",
        "format",
        "range",
        "exclusive",
        "unknown_field",
        "unsupported",
        "config_invalid",
    }
    assert {reason.value for reason in UnavailableReason} == {
        "store_unavailable",
        "search_index_unavailable",
        "timeout",
        "malformed",
    }
    assert {state.value for state in LockState} == {
        "none",
        "held_crawl",
        "held_delete",
        "lease_expired",
        "orphan",
        "just_acquired",
        "unknown",
    }
    assert {state.value for state in ComponentState} == {
        "normal",
        "abnormal",
        "undetermined",
        "not_configured",
    }


def test_the_values_are_plain_strings_for_json() -> None:
    assert ErrorCode.JOB_NOT_FOUND == "job_not_found"
    assert f"{UnavailableReason.TIMEOUT}" == "timeout"


def test_an_admin_api_error_is_an_api_error_with_a_fixed_message() -> None:
    error = job_not_found()

    assert isinstance(error, ApiError)
    assert (error.status_code, error.code, error.message) == (
        404,
        "job_not_found",
        "the job is not found",
    )
    assert error.retryable is False
    assert error.details is None


def test_every_error_code_used_by_a_generator_has_a_message() -> None:
    for error in (
        invalid_request(),
        unavailable(),
        source_config_not_found(),
        job_not_found(),
        config_invalid([], "message"),
        crawler_error(),
        crawler_unreachable(),
        crawler_response_lost(),
    ):
        assert error.message
        assert error.code in {code.value for code in ErrorCode}


@pytest.mark.parametrize("code", list(ErrorCode))
def test_every_error_code_has_a_fixed_english_message(code: ErrorCode) -> None:
    """未定義の code で `KeyError` にならない(エラー応答の組み立てが 500 にならない)。"""
    error = AdminApiError(code, 400)

    assert error.message.isascii()
    assert error.message != ""
    assert error.message.strip() == error.message


@pytest.mark.parametrize(
    ("code", "message"),
    [
        # B 2.5・2.7 の例が出典の文言。残りは実装側で補った文(B に規定がない)。
        (ErrorCode.CONFIG_INVALID, "connector_config is invalid"),
        (ErrorCode.LOCK_HELD, "the source is locked by another job"),
    ],
)
def test_the_messages_that_b_gives_as_examples_are_fixed(code: ErrorCode, message: str) -> None:
    assert AdminApiError(code, 400).message == message


def test_invalid_request_without_violations_has_no_details() -> None:
    error = invalid_request()

    assert (error.status_code, error.code, error.details) == (400, "invalid_request", None)


def test_invalid_request_lists_every_violation_with_field_and_reason() -> None:
    error = invalid_request(
        [
            FieldViolation("ttl_days", Reason.EXCLUSIVE),
            FieldViolation("connector_config.root", Reason.CONFIG_INVALID, "must be absolute"),
        ]
    )

    assert error.details == {
        "errors": [
            {"field": "ttl_days", "reason": "exclusive"},
            {
                "field": "connector_config.root",
                "reason": "config_invalid",
                "detail": "must be absolute",
            },
        ]
    }


def test_unavailable_is_a_retryable_503() -> None:
    error = unavailable()

    assert (error.status_code, error.code, error.retryable) == (503, "unavailable", True)


def test_the_error_response_has_the_unified_shape() -> None:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)

    @app.get("/invalid")
    async def raise_invalid() -> None:
        raise invalid_request([FieldViolation("page", Reason.RANGE)])

    @app.get("/unavailable")
    async def raise_unavailable() -> None:
        raise unavailable()

    install_common_http(app)
    client = TestClient(app)

    assert client.get("/invalid").json() == {
        "error": {
            "code": "invalid_request",
            "message": "the request is invalid",
            "retryable": False,
            "details": {"errors": [{"field": "page", "reason": "range"}]},
        }
    }
    response = client.get("/unavailable")
    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "unavailable",
            "message": "the data store is unavailable",
            "retryable": True,
        }
    }


def test_config_invalid_lists_the_decomposed_violation_and_the_crawler_message() -> None:
    error = config_invalid(
        [FieldViolation("connector_config.root", Reason.CONFIG_INVALID, "must be absolute")],
        "root: must be absolute",
    )

    assert (error.status_code, error.code, error.retryable) == (400, "config_invalid", False)
    assert error.details == {
        "errors": [
            {
                "field": "connector_config.root",
                "reason": "config_invalid",
                "detail": "must be absolute",
            }
        ],
        "crawler_message": "root: must be absolute",
    }


def test_config_invalid_without_a_decomposition_has_empty_errors() -> None:
    error = config_invalid([], "something unexpected")

    assert error.details == {"errors": [], "crawler_message": "something unexpected"}


@pytest.mark.parametrize(
    ("error", "status_code", "code", "retryable", "details"),
    [
        (crawler_error(), 502, "crawler_error", False, None),
        (crawler_unreachable(), 503, "crawler_unreachable", True, None),
        (crawler_response_lost(), 504, "crawler_response_lost", False, {"outcome_unknown": True}),
    ],
)
def test_the_crawler_failures_have_the_status_retryability_and_details_of_the_specification(
    error: AdminApiError,
    status_code: int,
    code: str,
    retryable: bool,
    details: dict[str, object] | None,
) -> None:
    """B 2.3: 届かなかった(503)は再試行してよく、応答が来なかった(504)は結果が不明。"""
    assert (error.status_code, error.code, error.retryable, error.details) == (
        status_code,
        code,
        retryable,
        details,
    )
