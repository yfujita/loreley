import json
import logging

import pytest

from loreley_api.common.http.errors import (
    INTERNAL_ERROR_MESSAGE,
    ApiError,
    describe_origin,
    error_response,
    internal_error_response,
    log_unexpected_error,
)

EXCEPTION_MESSAGE = "SENTINEL-EXCEPTION-MESSAGE"


def body_of(response) -> dict:
    return json.loads(response.body)


def test_the_error_body_has_code_message_and_retryable() -> None:
    response = error_response(409, "conflict", "a fixed message")

    assert response.status_code == 409
    assert response.media_type == "application/json"
    assert body_of(response) == {
        "error": {"code": "conflict", "message": "a fixed message", "retryable": False}
    }


def test_details_are_omitted_when_there_are_none_and_kept_when_given() -> None:
    without = body_of(error_response(400, "invalid_request", "m"))
    with_details = body_of(
        error_response(
            400, "invalid_request", "m", retryable=True, details={"errors": [{"field": "a"}]}
        )
    )

    assert "details" not in without["error"]
    assert with_details["error"]["details"] == {"errors": [{"field": "a"}]}
    assert with_details["error"]["retryable"] is True


def test_the_internal_error_response_is_a_fixed_500() -> None:
    response = internal_error_response()

    assert response.status_code == 500
    assert body_of(response) == {
        "error": {"code": "internal_error", "message": INTERNAL_ERROR_MESSAGE, "retryable": False}
    }


def test_an_api_error_keeps_what_the_feature_gave() -> None:
    error = ApiError(503, "unavailable", "try later", retryable=True, details={"k": 1})

    assert (error.status_code, error.code, error.message) == (503, "unavailable", "try later")
    assert error.retryable is True
    assert error.details == {"k": 1}
    assert str(error) == "try later"


def test_an_api_error_is_not_retryable_and_has_no_details_by_default() -> None:
    error = ApiError(404, "source_not_found", "not found")

    assert error.retryable is False
    assert error.details is None


def raise_with_sentinel() -> None:
    raise RuntimeError(EXCEPTION_MESSAGE)


def test_the_origin_is_the_innermost_frame_without_the_message() -> None:
    with pytest.raises(RuntimeError) as error_info:
        raise_with_sentinel()

    origin = describe_origin(error_info.value)

    assert origin.startswith("http/test_errors.py:")
    assert origin.endswith(" raise_with_sentinel")
    assert EXCEPTION_MESSAGE not in origin


def test_the_origin_of_an_exception_that_was_never_raised_is_unknown() -> None:
    assert describe_origin(RuntimeError("x")) == "unknown"


def test_an_unexpected_error_is_logged_by_class_name_and_origin_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with pytest.raises(RuntimeError) as error_info:
        raise_with_sentinel()

    with caplog.at_level(logging.DEBUG):
        log_unexpected_error(error_info.value)

    (record,) = caplog.records
    assert record.levelno == logging.ERROR
    assert record.getMessage().startswith("request failed unexpectedly: error=RuntimeError origin=")
    assert record.exc_info is None
    assert EXCEPTION_MESSAGE not in caplog.text
