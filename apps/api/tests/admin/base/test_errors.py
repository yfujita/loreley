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
    for error in (invalid_request(), unavailable(), source_config_not_found(), job_not_found()):
        assert error.message
        assert error.code in {code.value for code in ErrorCode}


def test_a_code_without_a_message_is_a_programming_error() -> None:
    with pytest.raises(KeyError):
        AdminApiError(ErrorCode.LOCK_HELD, 409)


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
