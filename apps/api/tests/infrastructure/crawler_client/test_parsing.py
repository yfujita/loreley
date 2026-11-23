"""Crawler の応答の解釈(B 9.1。C 4.1・4.2。C 11章 1)。"""

import json
from typing import Any

import pytest

from loreley_api.infrastructure.crawler_client import (
    ConfigInvalidMessage,
    ConfigViolation,
    CrawlerContractViolation,
    CrawlerRejected,
    CrawlerSucceeded,
)
from loreley_api.infrastructure.crawler_client.parsing import (
    RESPONSE_MAX_BYTES,
    collect_within_limit,
    interpret_response,
)

OK = frozenset({200})
ACCEPTED = frozenset({202})
BOTH = frozenset({200, 202})


def body_of(payload: Any) -> bytes:
    return json.dumps(payload).encode()


def error_body(code: object, *, message: object = "fixed", details: object = None) -> bytes:
    error: dict[str, object] = {"code": code, "message": message, "retryable": False}
    if details is not None:
        error["details"] = details
    return body_of({"error": error})


def test_a_success_status_with_a_json_object_is_succeeded() -> None:
    result = interpret_response(202, body_of({"job_id": "j"}), success_statuses=ACCEPTED)

    assert result == CrawlerSucceeded(202, {"job_id": "j"})


@pytest.mark.parametrize("status", [200, 202])
def test_every_listed_success_status_is_accepted(status: int) -> None:
    assert isinstance(
        interpret_response(status, body_of({}), success_statuses=BOTH), CrawlerSucceeded
    )


@pytest.mark.parametrize("status", [100, 101, 200, 201, 204, 206, 299])
def test_a_2xx_or_1xx_status_that_the_api_does_not_expect_is_a_contract_violation(
    status: int,
) -> None:
    result = interpret_response(status, body_of({}), success_statuses=ACCEPTED)

    assert result == CrawlerContractViolation("unexpected_status", status)


@pytest.mark.parametrize("status", [300, 301, 302, 303, 307, 308, 399])
def test_a_redirect_is_a_contract_violation_even_with_a_json_body(status: int) -> None:
    result = interpret_response(status, body_of({"error": {"code": "x"}}), success_statuses=OK)

    assert result == CrawlerContractViolation("redirect", status)


@pytest.mark.parametrize(
    "body",
    [b"", b"not json", b"[]", b'"text"', b"null", b"1", b"\xff\xfe", b"{", b'{"a": NaN}'],
)
def test_a_success_body_that_is_not_a_json_object_is_a_contract_violation(body: bytes) -> None:
    result = interpret_response(200, body, success_statuses=OK)

    assert result == CrawlerContractViolation("malformed_body", 200)


def test_a_deeply_nested_body_is_a_contract_violation_not_a_crash() -> None:
    body = b"[" * 100_000 + b"]" * 100_000

    assert interpret_response(200, body, success_statuses=OK) == CrawlerContractViolation(
        "malformed_body", 200
    )


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_a_non_finite_json_constant_is_rejected(constant: str) -> None:
    body = f'{{"ratio_threshold": {constant}}}'.encode()

    assert interpret_response(200, body, success_statuses=OK) == CrawlerContractViolation(
        "malformed_body", 200
    )


def test_an_error_keeps_status_code_and_details_only() -> None:
    details = {"existing_job": {"job_id": "j"}}
    body = error_body("lock_held", message="SENTINEL-MESSAGE", details=details)

    result = interpret_response(409, body, success_statuses=ACCEPTED)

    assert result == CrawlerRejected(409, "lock_held", details, config_invalid=None)
    assert "SENTINEL-MESSAGE" not in repr(result)


@pytest.mark.parametrize("status", [400, 404, 409, 500, 502, 503, 504, 599])
def test_an_error_status_with_a_crawler_error_body_is_rejected(status: int) -> None:
    result = interpret_response(status, error_body("unavailable"), success_statuses=OK)

    assert result == CrawlerRejected(status, "unavailable", None, config_invalid=None)


@pytest.mark.parametrize("details", [None, [], "text", 1, True])
def test_details_that_is_not_an_object_is_dropped(details: object) -> None:
    body = body_of({"error": {"code": "x", "details": details}})

    result = interpret_response(409, body, success_statuses=OK)

    assert isinstance(result, CrawlerRejected)
    assert result.details is None


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"<html>Bad Gateway</html>",
        b"[]",
        b"{}",
        body_of({"error": "text"}),
        body_of({"error": []}),
        body_of({"error": {}}),
        body_of({"error": {"message": "no code"}}),
        body_of({"error": {"code": None}}),
        body_of({"error": {"code": 409}}),
        body_of({"error": {"code": ""}}),
        body_of({"code": "lock_held"}),
    ],
)
def test_an_error_body_without_an_error_code_is_a_contract_violation(body: bytes) -> None:
    result = interpret_response(502, body, success_statuses=OK)

    assert result == CrawlerContractViolation("malformed_error", 502)


def test_config_invalid_carries_the_decomposed_message() -> None:
    body = error_body("config_invalid", message="root: `/` で始まる絶対パスでない")

    result = interpret_response(400, body, success_statuses=OK)

    assert result == CrawlerRejected(
        400,
        "config_invalid",
        None,
        config_invalid=ConfigInvalidMessage(
            "root: `/` で始まる絶対パスでない",
            ConfigViolation("connector_config.root", "`/` で始まる絶対パスでない"),
        ),
    )


def test_config_invalid_with_an_undecomposable_message_keeps_the_message() -> None:
    result = interpret_response(
        400, error_body("config_invalid", message="free text"), success_statuses=OK
    )

    assert isinstance(result, CrawlerRejected)
    assert result.config_invalid == ConfigInvalidMessage("free text", None)


@pytest.mark.parametrize("message", [None, 1, ["a"], {"a": 1}])
def test_config_invalid_without_a_string_message_is_a_contract_violation(message: object) -> None:
    body = body_of({"error": {"code": "config_invalid", "message": message}})

    assert interpret_response(400, body, success_statuses=OK) == CrawlerContractViolation(
        "malformed_error", 400
    )


def test_collect_within_limit_joins_chunks() -> None:
    assert collect_within_limit([b"ab", b"", b"cd"], 10) == b"abcd"


def test_collect_within_limit_accepts_exactly_the_limit() -> None:
    assert collect_within_limit([b"abc", b"de"], 5) == b"abcde"


def test_collect_within_limit_stops_reading_when_the_limit_is_exceeded() -> None:
    consumed: list[bytes] = []

    def chunks() -> Any:
        for chunk in (b"abc", b"def", b"ghi"):
            consumed.append(chunk)
            yield chunk

    assert collect_within_limit(chunks(), 5) is None
    assert consumed == [b"abc", b"def"]  # 3 つ目は読まない


def test_the_response_limit_is_one_mebibyte_like_the_admin_constant() -> None:
    from loreley_api.admin.base.constants import CRAWLER_RESPONSE_MAX_BYTES

    assert RESPONSE_MAX_BYTES == CRAWLER_RESPONSE_MAX_BYTES == 1024 * 1024
