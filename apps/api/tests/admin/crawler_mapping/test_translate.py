"""Crawler クライアントの返り値の写像(B 2.6・9.2。C 11章 1〜4)。

B 9.2 の API ごとの表を、表駆動で 1 行ずつ確かめる(`ROWS`)。表にない組み合わせは 502 になること、
送信の失敗・契約外の応答は API によらず同じであること、400 `invalid_request` の項目の写し方、
`existing_job` の取り込み、`config_invalid` の受け渡しも確かめる。
"""

from typing import Any

import pytest

from loreley_api.admin.base.codes import LockState
from loreley_api.admin.base.errors import AdminApiError
from loreley_api.admin.crawler_mapping import (
    CrawlerOperation,
    RequestedOptions,
    needs_lock_state,
    translate,
)
from loreley_api.admin.crawler_mapping.table import TABLE
from loreley_api.infrastructure.crawler_client import (
    ConfigInvalidMessage,
    ConfigViolation,
    CrawlerContractViolation,
    CrawlerRejected,
    CrawlerResult,
    CrawlerSucceeded,
    CrawlerTransportFailed,
)
from tests.admin.crawler_mapping.mapping_rows import (
    CANCEL,
    CRAWLER_ERROR,
    EXISTING_JOB,
    LOCK_HELD_DETAILS,
    REGISTER,
    RELEASE,
    REQUESTED,
    ROWS,
    START_CRAWL,
    START_DELETE,
    UPDATE,
    field_errors,
    rejected,
)
from tests.secret_assertions import assert_secret_absent


def translate_error(
    operation: CrawlerOperation, result: CrawlerResult, **options: Any
) -> AdminApiError:
    translated = translate(operation, result, **options)
    assert isinstance(translated, AdminApiError), translated
    return translated


def describe(error: AdminApiError) -> tuple[int, str, bool, dict[str, Any] | None]:
    return error.status_code, error.code, error.retryable, error.details


@pytest.mark.parametrize(
    ("operation", "crawler_response", "expected"),
    ROWS,
    ids=[f"{op.value}-{r.status}-{r.code}" for op, r, _ in ROWS],
)
def test_each_row_of_the_crawler_mapping_table_of_the_specification(
    operation: CrawlerOperation, crawler_response: CrawlerRejected, expected: tuple[Any, ...]
) -> None:
    error = translate_error(
        operation, crawler_response, lock_state=LockState.HELD_CRAWL, requested=REQUESTED
    )

    assert describe(error) == expected


def test_a_registration_conflict_carries_the_status_of_the_existing_source() -> None:
    for existing_status in ("active", "deleting", None):
        error = translate_error(
            REGISTER, rejected(409, "source_already_exists", {"status": existing_status})
        )

        assert error.details == {"status": existing_status}


@pytest.mark.parametrize("details", [None, {}, {"status": 1}, {"status": ["active"]}])
def test_an_unreadable_status_of_a_conflict_becomes_null(details: dict[str, Any] | None) -> None:
    error = translate_error(REGISTER, rejected(409, "source_already_exists", details))

    assert error.details == {"status": None}


# --- 表の網羅: B の表にない組み合わせは 502 ---

# Crawler が返しうる `(status, code)`(crawler-api 3.3・4章)。
KNOWN_CRAWLER_RESPONSES: list[tuple[int, str]] = [
    (400, "invalid_request"),
    (400, "config_invalid"),
    (404, "source_config_not_found"),
    (404, "job_not_found"),
    (404, "not_found"),
    (405, "method_not_allowed"),
    (409, "lock_held"),
    (409, "lock_in_use"),
    (409, "source_deleting"),
    (409, "maintenance_enabled"),
    (409, "source_already_exists"),
    (409, "job_not_cancellable"),
    (409, "job_already_finished"),
    (500, "internal_error"),
    (503, "unavailable"),
]
UNKNOWN_RESPONSES: list[tuple[int, str]] = [
    (418, "teapot"),
    (400, "something_new"),
    (409, "something_new"),
    (404, "http_error"),
    (422, "invalid_request"),
    (502, "bad_gateway"),
    (500, "unavailable"),  # 既知の code でもステータスが違う
    (503, "internal_error"),
    (404, ""),
]


@pytest.mark.parametrize("operation", list(CrawlerOperation))
@pytest.mark.parametrize(("status", "code"), KNOWN_CRAWLER_RESPONSES + UNKNOWN_RESPONSES)
def test_a_combination_that_is_not_in_the_table_is_a_crawler_error(
    operation: CrawlerOperation, status: int, code: str
) -> None:
    result = rejected(
        status,
        code,
        {"existing_job": EXISTING_JOB, "status": "active", "errors": []},
        ConfigInvalidMessage("root: x", ConfigViolation("connector_config.root", "x")),
    )
    in_table = (operation, status, code) in TABLE

    translated = translate(operation, result, lock_state=LockState.NONE, requested=REQUESTED)

    assert isinstance(translated, AdminApiError)
    if not in_table:
        assert describe(translated) == CRAWLER_ERROR


def test_the_table_has_exactly_the_rows_of_the_specification() -> None:
    """表の行は、B 9.2 の API ごとの表の行(B が 502 と明記する行を含む)と一致する。"""
    expected = {
        (REGISTER, 400, "invalid_request"),
        (REGISTER, 400, "config_invalid"),
        (REGISTER, 409, "source_already_exists"),
        (REGISTER, 500, "internal_error"),
        (REGISTER, 503, "unavailable"),
        (UPDATE, 400, "invalid_request"),
        (UPDATE, 400, "config_invalid"),
        (UPDATE, 404, "source_config_not_found"),
        (UPDATE, 409, "source_deleting"),
        (UPDATE, 500, "internal_error"),
        (UPDATE, 503, "unavailable"),
        (START_DELETE, 404, "source_config_not_found"),
        (START_DELETE, 409, "maintenance_enabled"),
        (START_DELETE, 409, "lock_held"),
        (START_DELETE, 400, "invalid_request"),
        (START_DELETE, 503, "unavailable"),
        (START_DELETE, 500, "internal_error"),
        (START_CRAWL, 404, "source_config_not_found"),
        (START_CRAWL, 409, "source_deleting"),
        (START_CRAWL, 409, "maintenance_enabled"),
        (START_CRAWL, 409, "lock_held"),
        (START_CRAWL, 400, "invalid_request"),
        (START_CRAWL, 503, "unavailable"),
        (START_CRAWL, 500, "internal_error"),
        (CANCEL, 404, "job_not_found"),
        (CANCEL, 400, "invalid_request"),
        (CANCEL, 404, "not_found"),
        (CANCEL, 409, "job_not_cancellable"),
        (CANCEL, 409, "job_already_finished"),
        (CANCEL, 503, "unavailable"),
        (CANCEL, 500, "internal_error"),
        (RELEASE, 409, "lock_in_use"),
        (RELEASE, 400, "invalid_request"),
        (RELEASE, 503, "unavailable"),
        (RELEASE, 500, "internal_error"),
    }

    assert set(TABLE) == expected


# --- 成功・送信の失敗・契約外の応答(API によらない) ---


@pytest.mark.parametrize("operation", list(CrawlerOperation))
def test_a_success_is_returned_unchanged(operation: CrawlerOperation) -> None:
    success = CrawlerSucceeded(202, {"job_id": "j"})

    assert translate(operation, success) is success


@pytest.mark.parametrize("operation", list(CrawlerOperation))
@pytest.mark.parametrize(
    "reason", ["name_resolution", "connection_failed", "connect_timeout", "tls_failure"]
)
def test_a_failure_before_sending_is_crawler_unreachable_and_retryable(
    operation: CrawlerOperation, reason: Any
) -> None:
    error = translate_error(operation, CrawlerTransportFailed("before_send", reason))

    assert describe(error) == (503, "crawler_unreachable", True, None)


@pytest.mark.parametrize("operation", list(CrawlerOperation))
@pytest.mark.parametrize("reason", ["response_timeout", "connection_lost", "http_error"])
def test_a_lost_response_is_crawler_response_lost_with_an_unknown_outcome(
    operation: CrawlerOperation, reason: Any
) -> None:
    error = translate_error(operation, CrawlerTransportFailed("after_send", reason))

    assert describe(error) == (504, "crawler_response_lost", False, {"outcome_unknown": True})


@pytest.mark.parametrize("operation", list(CrawlerOperation))
@pytest.mark.parametrize(
    ("reason", "status"),
    [
        ("redirect", 307),
        ("unexpected_status", 200),
        ("body_too_large", 202),
        ("malformed_body", 202),
        ("malformed_error", 502),
    ],
)
def test_a_contract_violation_is_a_crawler_error(
    operation: CrawlerOperation, reason: Any, status: int
) -> None:
    error = translate_error(operation, CrawlerContractViolation(reason, status))

    assert describe(error) == CRAWLER_ERROR


# --- 400 invalid_request の項目の写し方(B 2.6) ---


@pytest.mark.parametrize("operation", [REGISTER, UPDATE])
@pytest.mark.parametrize(
    ("crawler_field", "admin_field"),
    [
        ("connector_type", "connector_type"),
        ("connector_config", "connector_config"),
        ("ratio_threshold", "ratio_threshold_percent"),
        ("min_delete_count", "min_delete_count"),
        ("schedule_cron", "schedule_cron"),
    ],
)
def test_a_crawler_field_name_is_renamed_to_the_admin_field_name(
    operation: CrawlerOperation, crawler_field: str, admin_field: str
) -> None:
    error = translate_error(
        operation, rejected(400, "invalid_request", field_errors((crawler_field, "type")))
    )

    assert error.details == field_errors((admin_field, "type"))


@pytest.mark.parametrize("ttl_field", ["ttl_days", "ttl_seconds"])
def test_a_ttl_violation_is_reported_on_the_field_the_request_used(ttl_field: Any) -> None:
    error = translate_error(
        REGISTER,
        rejected(400, "invalid_request", field_errors(("ttl", "type"))),
        ttl_field=ttl_field,
    )

    assert error.details == field_errors((ttl_field, "type"))


def test_the_ttl_violation_defaults_to_the_seconds_field() -> None:
    error = translate_error(UPDATE, rejected(400, "invalid_request", field_errors(("ttl", "type"))))

    assert error.details == field_errors(("ttl_seconds", "type"))


def test_the_reason_is_kept_as_the_crawler_returned_it() -> None:
    crawler_response = rejected(
        400,
        "invalid_request",
        field_errors(
            ("connector_type", "unsupported"),
            ("connector_config", "format"),
            ("schedule_cron", "format"),
            ("ratio_threshold", "type"),
        ),
    )

    error = translate_error(REGISTER, crawler_response)

    assert error.details == field_errors(
        ("connector_type", "unsupported"),
        ("connector_config", "format"),
        ("schedule_cron", "format"),
        ("ratio_threshold_percent", "type"),
    )


def test_only_the_fields_that_can_be_renamed_are_returned_and_the_others_are_dropped() -> None:
    crawler_response = rejected(
        400,
        "invalid_request",
        field_errors(
            ("source_id", "format"), ("min_delete_count", "type"), ("extra", "unknown_field")
        ),
    )

    error = translate_error(REGISTER, crawler_response)

    assert error.details == field_errors(("min_delete_count", "type"))


@pytest.mark.parametrize(
    "details",
    [
        field_errors(("source_id", "format")),
        field_errors(("body", "type")),
        field_errors(("extra", "unknown_field")),
        field_errors(("status", "read_only"), ("updated_at", "read_only")),
        field_errors(("job_id", "format")),  # EP-03・04 に job_id はない
        field_errors(("ttl", "read_only")),  # 知らない reason は写さない
        field_errors(),
        {"errors": "not a list"},
        {"errors": [None, 1, "x", {"reason": "type"}, {"field": 1, "reason": "type"}]},
        {},
        None,
    ],
)
def test_a_registration_rejection_without_a_renamable_field_is_a_crawler_error(
    details: dict[str, Any] | None,
) -> None:
    error = translate_error(REGISTER, rejected(400, "invalid_request", details))

    assert describe(error) == CRAWLER_ERROR


# --- EP-07: job_id 起因の 404 ---


@pytest.mark.parametrize(
    "details",
    [
        field_errors(("job_id", "format")),
        field_errors(("job_id", "format"), ("body", "type")),
        field_errors(("source_id", "format"), ("job_id", "format")),
    ],
)
def test_a_cancel_rejection_caused_by_the_job_id_is_a_job_not_found(
    details: dict[str, Any],
) -> None:
    error = translate_error(CANCEL, rejected(400, "invalid_request", details))

    assert describe(error) == (404, "job_not_found", False, None)


@pytest.mark.parametrize(
    "details",
    [
        field_errors(("source_id", "format")),
        field_errors(("body", "type")),
        {},
        None,
        {"errors": 1},
    ],
)
def test_a_cancel_rejection_not_caused_by_the_job_id_is_a_crawler_error(
    details: dict[str, Any] | None,
) -> None:
    error = translate_error(CANCEL, rejected(400, "invalid_request", details))

    assert describe(error) == CRAWLER_ERROR


@pytest.mark.parametrize("operation", [START_CRAWL, START_DELETE, RELEASE, REGISTER, UPDATE])
def test_a_not_found_or_a_job_id_violation_of_an_operation_with_a_source_id_is_a_crawler_error(
    operation: CrawlerOperation,
) -> None:
    """`source_id` は文字種を検証済みなので、同じ応答は Admin API の不具合(B 2.6)。"""
    for response in (
        rejected(404, "not_found"),
        rejected(400, "invalid_request", field_errors(("job_id", "format"))),
    ):
        assert describe(translate_error(operation, response)) == CRAWLER_ERROR


# --- 409 lock_held・lock_in_use の付随情報 ---


def test_the_existing_job_is_copied_from_the_crawler_and_lock_state_is_the_derived_one() -> None:
    error = translate_error(
        START_DELETE,
        rejected(409, "lock_held", {"existing_job": EXISTING_JOB}),
        lock_state=LockState.LEASE_EXPIRED,
    )

    assert error.details == {"existing_job": EXISTING_JOB, "lock_state": "lease_expired"}


def test_the_lock_state_is_unknown_unless_the_caller_derived_it() -> None:
    error = translate_error(RELEASE, rejected(409, "lock_in_use", {"existing_job": EXISTING_JOB}))

    assert error.status_code == 409
    assert error.details == {"existing_job": EXISTING_JOB, "lock_state": "unknown"}


def test_a_lock_held_of_start_crawl_reports_the_options_that_were_not_applied() -> None:
    error = translate_error(
        START_CRAWL,
        rejected(409, "lock_held", {"existing_job": EXISTING_JOB}),
        requested=RequestedOptions(force_delete=False, rewrite_mode=True),
    )

    assert error.details is not None
    assert error.details["options_applied"] is False
    assert error.details["requested"] == {"force_delete": False, "rewrite_mode": True}


def test_a_lock_held_of_start_crawl_needs_the_requested_options() -> None:
    with pytest.raises(ValueError, match="requested"):
        translate(START_CRAWL, rejected(409, "lock_held", {"existing_job": EXISTING_JOB}))


def test_the_missing_requested_options_do_not_matter_for_the_other_operations() -> None:
    error = translate_error(
        START_DELETE, rejected(409, "lock_held", {"existing_job": EXISTING_JOB})
    )

    assert error.details is not None
    assert "requested" not in error.details
    assert "options_applied" not in error.details


def test_the_existing_job_keeps_only_the_five_known_fields() -> None:
    existing_job = {**EXISTING_JOB, "owner_token": "SENTINEL-EXTRA", "extra": {"nested": 1}}

    error = translate_error(
        START_DELETE, rejected(409, "lock_held", {"existing_job": existing_job, "other": "x"})
    )

    assert error.details == LOCK_HELD_DETAILS | {"lock_state": "unknown"}
    assert_secret_absent("SENTINEL-EXTRA", response_text=repr(error.details))


def test_unreadable_values_of_the_existing_job_become_null() -> None:
    """ジョブ記録がない(孤児ロック)・読めない値は `null`(B 2.7)。"""
    existing_job = {
        "job_id": "j",
        "job_type": None,
        "status": 1,
        "trigger": ["schedule"],
        # `lease_expires_at` の番兵値は、文字列なので変換せずそのまま通す(I-73)。
        "lease_expires_at": "0001-01-01T00:00:00.000Z",
    }

    error = translate_error(RELEASE, rejected(409, "lock_in_use", {"existing_job": existing_job}))

    assert error.details is not None
    assert error.details["existing_job"] == {
        "job_id": "j",
        "job_type": None,
        "status": None,
        "trigger": None,
        "lease_expires_at": "0001-01-01T00:00:00.000Z",
    }


def test_missing_optional_fields_of_the_existing_job_are_null() -> None:
    error = translate_error(
        RELEASE, rejected(409, "lock_in_use", {"existing_job": {"job_id": "j"}})
    )

    assert error.details is not None
    assert error.details["existing_job"] == {
        "job_id": "j",
        "job_type": None,
        "status": None,
        "trigger": None,
        "lease_expires_at": None,
    }


@pytest.mark.parametrize(
    "details",
    [
        None,
        {},
        {"existing_job": None},
        {"existing_job": "job-1"},
        {"existing_job": []},
        {"existing_job": {}},
        {"existing_job": {"job_id": None}},
        {"existing_job": {"job_id": 1}},
        {"existing_job": {"status": "running"}},
    ],
)
@pytest.mark.parametrize(
    ("operation", "status", "code"),
    [
        (START_CRAWL, 409, "lock_held"),
        (START_DELETE, 409, "lock_held"),
        (RELEASE, 409, "lock_in_use"),
    ],
)
def test_a_lock_conflict_without_a_readable_existing_job_is_a_crawler_error(
    operation: CrawlerOperation, status: int, code: str, details: dict[str, Any] | None
) -> None:
    error = translate_error(
        operation, rejected(status, code, details), lock_state=LockState.NONE, requested=REQUESTED
    )

    assert describe(error) == CRAWLER_ERROR


def test_needs_lock_state_is_true_only_for_the_lock_conflicts() -> None:
    lock_held = rejected(409, "lock_held", {"existing_job": EXISTING_JOB})
    lock_in_use = rejected(409, "lock_in_use", {"existing_job": EXISTING_JOB})

    assert needs_lock_state(START_CRAWL, lock_held)
    assert needs_lock_state(START_DELETE, lock_held)
    assert needs_lock_state(RELEASE, lock_in_use)
    # 表にない組み合わせ(その API の 409 ではない)・ほかの失敗・成功は、読まなくてよい。
    assert not needs_lock_state(RELEASE, lock_held)
    assert not needs_lock_state(REGISTER, lock_held)
    assert not needs_lock_state(START_CRAWL, rejected(409, "source_deleting"))
    assert not needs_lock_state(CANCEL, rejected(409, "job_already_finished", {"status": "failed"}))
    assert not needs_lock_state(START_CRAWL, CrawlerSucceeded(202, {}))
    assert not needs_lock_state(
        START_CRAWL, CrawlerTransportFailed("after_send", "response_timeout")
    )
    assert not needs_lock_state(START_CRAWL, CrawlerContractViolation("redirect", 307))


@pytest.mark.parametrize("status", [None, 3, ["failed"], {"a": 1}])
def test_an_unreadable_status_of_job_already_finished_becomes_null(status: object) -> None:
    error = translate_error(CANCEL, rejected(409, "job_already_finished", {"status": status}))

    assert error.details == {"status": None}


# --- config_invalid(B 2.5。C 11章 4) ---


@pytest.mark.parametrize("operation", [REGISTER, UPDATE])
def test_a_decomposed_config_invalid_names_the_field_and_keeps_the_crawler_message(
    operation: CrawlerOperation,
) -> None:
    message = "include_patterns[2]: `\\` を含む(エスケープはない)"
    violation = ConfigViolation(
        "connector_config.include_patterns[2]", "`\\` を含む(エスケープはない)"
    )

    error = translate_error(
        operation, rejected(400, "config_invalid", None, ConfigInvalidMessage(message, violation))
    )

    assert describe(error) == (
        400,
        "config_invalid",
        False,
        {
            "errors": [
                {
                    "field": "connector_config.include_patterns[2]",
                    "reason": "config_invalid",
                    "detail": "`\\` を含む(エスケープはない)",
                }
            ],
            "crawler_message": message,
        },
    )


@pytest.mark.parametrize("operation", [REGISTER, UPDATE])
def test_an_undecomposable_config_invalid_has_empty_errors_and_the_crawler_message(
    operation: CrawlerOperation,
) -> None:
    error = translate_error(
        operation,
        rejected(400, "config_invalid", None, ConfigInvalidMessage("something new", None)),
    )

    assert describe(error) == (
        400,
        "config_invalid",
        False,
        {"errors": [], "crawler_message": "something new"},
    )


def test_a_config_invalid_without_a_parsed_message_is_a_crawler_error() -> None:
    """クライアントは `code=config_invalid` なら必ず分解結果を持たせる。持たなければ契約外。"""
    error = translate_error(REGISTER, rejected(400, "config_invalid", None, None))

    assert describe(error) == CRAWLER_ERROR


@pytest.mark.parametrize("operation", [START_CRAWL, START_DELETE, CANCEL, RELEASE])
def test_a_config_invalid_from_an_api_that_has_no_connector_config_is_a_crawler_error(
    operation: CrawlerOperation,
) -> None:
    result = rejected(400, "config_invalid", None, ConfigInvalidMessage("root: x", None))

    assert describe(translate_error(operation, result)) == CRAWLER_ERROR


# --- Crawler の message・入力値を出さない(B 9.1。A 5.2) ---


@pytest.mark.parametrize(("operation", "status", "code"), sorted(TABLE))
def test_the_crawler_message_and_unknown_details_never_reach_the_admin_error(
    operation: CrawlerOperation, status: int, code: str
) -> None:
    """`CrawlerRejected` は `message` を持たない。`details` の未知の項目も、写さない。"""
    crawler_response = rejected(
        status,
        code,
        {
            "message": "SENTINEL-MESSAGE",
            "note": "SENTINEL-NOTE",
            "existing_job": {**EXISTING_JOB, "job_id": "job-1", "path": "SENTINEL-PATH"},
            "errors": [
                {"field": "ttl", "reason": "type", "input": "SENTINEL-INPUT"},
                {"field": "job_id", "reason": "format", "value": "SENTINEL-VALUE"},
            ],
        },
    )

    error = translate_error(operation, crawler_response, requested=REQUESTED)

    for secret in (
        "SENTINEL-MESSAGE",
        "SENTINEL-NOTE",
        "SENTINEL-PATH",
        "SENTINEL-INPUT",
        "SENTINEL-VALUE",
    ):
        assert_secret_absent(secret, response_text=repr((error.message, error.code, error.details)))
