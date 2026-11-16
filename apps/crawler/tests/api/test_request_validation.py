"""リクエストの形式の検証(crawler-api 3.2・3.3 の `reason`)と、400 の本文に入力値を出さないこと。"""

import json
from typing import Any

import pytest

from tests.api.support import (
    BODY_SENTINEL,
    CONFIG_SECRET,
    SOURCE_ID,
    ApiEnv,
    new_source_body,
    update_body,
)

CRAWL = f"/sources/{SOURCE_ID}/crawl-jobs"
UPDATE = f"/sources/{SOURCE_ID}"


def errors_of(response) -> list[dict[str, str]]:
    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert error["retryable"] is False
    return error["details"]["errors"]


def without(body: dict[str, Any], *names: str) -> dict[str, Any]:
    return {key: value for key, value in body.items() if key not in names}


# --- 本文が JSON のオブジェクトでない ---


@pytest.mark.parametrize(
    "raw",
    [b"{", b"not json", b"\xff\xfe", b"[1", b'{"a": 1} trailing', b"'single'", b"nul\x00l"],
)
@pytest.mark.parametrize("path", ["/sources", UPDATE, CRAWL])
def test_a_body_that_is_not_json_is_400_without_details(api: ApiEnv, path: str, raw: bytes) -> None:
    api.jobs.seed_source()

    response = api.client.request("PUT" if path == UPDATE else "POST", path, content=raw)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert "details" not in response.json()["error"]


@pytest.mark.parametrize("raw", [b"[]", b"1", b'"text"', b"null", b"true"])
def test_a_json_value_that_is_not_an_object_is_a_type_error_of_the_body(
    api: ApiEnv, raw: bytes
) -> None:
    response = api.post("/sources", raw=raw)

    assert errors_of(response) == [{"field": "body", "reason": "type"}]


@pytest.mark.parametrize("depth", [5_000, 100_000])
@pytest.mark.parametrize("opening", ["[", '{"a": '], ids=["array", "object"])
def test_a_deeply_nested_body_is_400_not_a_crash(api: ApiEnv, depth: int, opening: str) -> None:
    closing = "]" if opening == "[" else "}"
    deep = ('{"connector_config": ' + opening * depth + closing * depth + "}").encode()

    response = api.post("/sources", raw=deep)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    if depth == 100_000:  # JSON として読めない(`RecursionError`)。`details` なし
        assert "details" not in error


def test_a_moderately_nested_connector_config_is_scanned_without_recursion(api: ApiEnv) -> None:
    nested: object = {"leaf": float("nan")}
    for _ in range(400):
        nested = [{"inner": nested}]
    raw = json.dumps(new_source_body(connector_config={"nested": nested})).encode()

    assert errors_of(api.post("/sources", raw=raw)) == [
        {"field": "connector_config", "reason": "type"}
    ]


@pytest.mark.parametrize(
    ("raw", "expected_status"),
    [
        (b'{"ttl": 1, "ttl": "x"}', 400),  # 後勝ち: 型の違反
        (b'{"ttl": "x", "ttl": 1}', 200),  # 後勝ち: 正しい値
    ],
)
def test_a_duplicate_key_is_decided_by_the_last_value(
    api: ApiEnv, raw: bytes, expected_status: int
) -> None:
    api.jobs.seed_source()
    body = json.loads(json.dumps(update_body()))
    del body["ttl"]
    rest = json.dumps(body)[1:-1].encode()  # 末尾の `}` を除いた項目
    request_body = raw[:-1] + b", " + rest + b"}"

    assert api.put(UPDATE, raw=request_body).status_code == expected_status


# --- クロール起動のボディ ---


@pytest.mark.parametrize(
    "body",
    [{"force_delete": "true"}, {"force_delete": 1}, {"force_delete": None}, {"force_delete": []}],
)
def test_force_delete_must_be_a_strict_boolean(api: ApiEnv, body: dict) -> None:
    api.jobs.seed_source()

    assert errors_of(api.post(CRAWL, body)) == [{"field": "force_delete", "reason": "type"}]
    assert api.jobs.job_ids() == []


@pytest.mark.parametrize("value", ["false", 0, 1.0, None])
def test_rewrite_mode_must_be_a_strict_boolean(api: ApiEnv, value: object) -> None:
    api.jobs.seed_source()

    assert errors_of(api.post(CRAWL, {"rewrite_mode": value})) == [
        {"field": "rewrite_mode", "reason": "type"}
    ]


def test_an_unknown_field_of_the_crawl_request_is_400_unknown_field(api: ApiEnv) -> None:
    api.jobs.seed_source()

    response = api.post(CRAWL, {"force_delete": True, "force": True, "rewriteMode": False})

    assert errors_of(response) == [
        {"field": "force", "reason": "unknown_field"},
        {"field": "rewriteMode", "reason": "unknown_field"},
    ]
    assert api.jobs.job_ids() == []


def test_a_malformed_source_id_in_the_path_is_400_before_the_body(api: ApiEnv) -> None:
    response = api.post("/sources/-bad/crawl-jobs", raw=b"not json")

    assert errors_of(response) == [{"field": "source_id", "reason": "format"}]


# --- 登録のボディ ---


@pytest.mark.parametrize(
    "missing",
    [
        "source_id",
        "connector_type",
        "connector_config",
        "ttl",
        "ratio_threshold",
        "min_delete_count",
    ],
)
def test_a_missing_required_field_of_a_registration_is_required(api: ApiEnv, missing: str) -> None:
    response = api.post("/sources", without(new_source_body(), missing))

    assert errors_of(response) == [{"field": missing, "reason": "required"}]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("source_id", 5, "type"),
        ("source_id", None, "type"),
        ("source_id", "", "format"),
        ("source_id", "a/b", "format"),
        ("source_id", "..", "format"),
        ("source_id", "-leading", "format"),
        ("source_id", "a b", "format"),
        ("source_id", "a%2Fb", "format"),
        ("source_id", "x" * 257, "format"),
        ("source_id", "a\nb", "format"),
        ("connector_type", 5, "type"),
        ("connector_type", "web", "unsupported"),
        ("connector_type", "", "unsupported"),
        ("connector_config", [], "type"),
        ("connector_config", "text", "type"),
        ("connector_config", None, "type"),
        ("ttl", "100", "type"),
        ("ttl", 1.5, "type"),
        ("ttl", 1.0, "type"),
        ("ttl", True, "type"),
        ("ttl", None, "type"),
        ("ratio_threshold", "0.3", "type"),
        ("ratio_threshold", True, "type"),
        ("ratio_threshold", None, "type"),
        ("min_delete_count", "1", "type"),
        ("min_delete_count", 2.5, "type"),
        ("min_delete_count", False, "type"),
        ("schedule_cron", 86_400, "type"),
        ("schedule_cron", True, "type"),
        ("schedule_cron", ["0 3 * * *"], "type"),
        ("schedule_cron", "", "format"),
        ("schedule_cron", "0 3 * *", "format"),
        ("schedule_cron", "0 0 3 * * *", "format"),  # 秒つきの 6 項目
        ("schedule_cron", "@daily", "format"),
        ("schedule_cron", "60 3 * * *", "format"),
        ("schedule_cron", "0 3 * * * ", "format"),
    ],
)
def test_each_value_rule_violation_of_a_registration_is_reported_with_its_reason(
    api: ApiEnv, field: str, value: object, reason: str
) -> None:
    response = api.post("/sources", new_source_body(**{field: value}))

    assert errors_of(response) == [{"field": field, "reason": reason}]
    assert api.sources_repository.record_ids() == []


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_a_non_finite_number_is_a_type_error_not_a_json_error(api: ApiEnv, constant: str) -> None:
    raw = (
        b'{"source_id": "docs-share", "connector_type": "file_system", '
        b'"connector_config": {"root": "/data"}, "ttl": 1, "min_delete_count": 1, '
        b'"ratio_threshold": ' + constant.encode() + b"}"
    )

    assert errors_of(api.post("/sources", raw=raw)) == [
        {"field": "ratio_threshold", "reason": "type"}
    ]


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "1e999"])
def test_a_non_finite_number_inside_the_connector_config_is_a_type_error(
    api: ApiEnv, constant: str
) -> None:
    raw = (
        b'{"source_id": "docs-share", "connector_type": "file_system", '
        b'"connector_config": {"nested": [{"x": ' + constant.encode() + b'}]}, "ttl": 1, '
        b'"min_delete_count": 1, "ratio_threshold": 0.5}'
    )

    assert errors_of(api.post("/sources", raw=raw)) == [
        {"field": "connector_config", "reason": "type"}
    ]
    assert api.connector_type.validated_configs == []


def test_a_lone_surrogate_inside_the_connector_config_is_a_format_error(api: ApiEnv) -> None:
    raw = json.dumps(new_source_body(connector_config={"root": "/data/\ud800"})).encode(
        "utf-8", errors="surrogatepass"
    )

    assert errors_of(api.post("/sources", raw=raw)) == [
        {"field": "connector_config", "reason": "format"}
    ]


@pytest.mark.parametrize("field", ["status", "updated_at"])
def test_a_server_set_field_in_a_registration_is_read_only(api: ApiEnv, field: str) -> None:
    response = api.post("/sources", new_source_body(**{field: "active"}))

    assert errors_of(response) == [{"field": field, "reason": "read_only"}]


def test_an_unknown_field_in_a_registration_is_unknown_field(api: ApiEnv) -> None:
    response = api.post("/sources", new_source_body(owner="someone"))

    assert errors_of(response) == [{"field": "owner", "reason": "unknown_field"}]


def test_all_problems_are_reported_in_a_fixed_order(api: ApiEnv) -> None:
    body = {"status": "active", "zzz": 1, "ttl": "x", "connector_type": "web", "aaa": 2}

    errors = errors_of(api.post("/sources", body))

    assert errors == [
        {"field": "source_id", "reason": "required"},
        {"field": "connector_config", "reason": "required"},
        {"field": "ratio_threshold", "reason": "required"},
        {"field": "min_delete_count", "reason": "required"},
        {"field": "status", "reason": "read_only"},
        {"field": "zzz", "reason": "unknown_field"},
        {"field": "aaa", "reason": "unknown_field"},
        {"field": "connector_type", "reason": "unsupported"},
        {"field": "ttl", "reason": "type"},
    ]


def test_an_unknown_field_name_is_shown_escaped_and_truncated(api: ApiEnv) -> None:
    body = new_source_body(**{"a\nb\ud800" + "x" * 500: 1})

    errors = errors_of(api.post("/sources", raw=json.dumps(body).encode("utf-8")))

    assert len(errors) == 1
    assert errors[0]["reason"] == "unknown_field"
    assert len(errors[0]["field"]) <= 100
    assert "\n" not in errors[0]["field"]


# --- 更新のボディ ---


@pytest.mark.parametrize(
    "missing", ["connector_config", "ttl", "ratio_threshold", "min_delete_count"]
)
def test_a_missing_required_field_of_an_update_is_required(api: ApiEnv, missing: str) -> None:
    api.jobs.seed_source()

    response = api.put(UPDATE, without(update_body(), missing))

    assert errors_of(response) == [{"field": missing, "reason": "required"}]


@pytest.mark.parametrize("field", ["source_id", "connector_type", "status", "updated_at"])
def test_a_field_fixed_by_the_path_or_registration_or_the_server_is_read_only_on_update(
    api: ApiEnv, field: str
) -> None:
    api.jobs.seed_source()
    value = {"source_id": SOURCE_ID, "connector_type": "file_system"}.get(field, "x")

    response = api.put(UPDATE, update_body(**{field: value}))

    assert errors_of(response) == [{"field": field, "reason": "read_only"}]


def test_an_update_never_changes_the_stored_record_when_the_request_is_malformed(
    api: ApiEnv,
) -> None:
    api.jobs.seed_source()
    before = api.sources_repository.body_of(SOURCE_ID)

    api.put(UPDATE, update_body(ttl="x"))

    assert api.sources_repository.body_of(SOURCE_ID) == before


def test_the_connector_type_is_not_checked_on_update_so_an_unsupported_one_is_read_only(
    api: ApiEnv,
) -> None:
    response = api.put(UPDATE, update_body(connector_type="web"))

    assert errors_of(response) == [{"field": "connector_type", "reason": "read_only"}]


def test_a_malformed_source_id_in_the_update_path_is_400(api: ApiEnv) -> None:
    response = api.put("/sources/-bad", update_body())

    assert errors_of(response) == [{"field": "source_id", "reason": "format"}]


def test_an_invalid_request_is_400_even_if_the_source_does_not_exist(api: ApiEnv) -> None:
    assert api.put(UPDATE, update_body(ttl="x")).status_code == 400


# --- 400 の本文に入力値を含めない ---


@pytest.mark.parametrize(
    "overrides",
    [
        {"ttl": BODY_SENTINEL},
        {"ratio_threshold": BODY_SENTINEL},
        {"min_delete_count": BODY_SENTINEL},
        {"schedule_cron": BODY_SENTINEL},
        {"source_id": BODY_SENTINEL + "/x"},
        {"connector_type": BODY_SENTINEL},
        {"status": BODY_SENTINEL},
        {"updated_at": BODY_SENTINEL},
        {"connector_config": BODY_SENTINEL},
    ],
)
def test_a_400_for_a_registration_never_contains_the_input_values(
    api: ApiEnv, overrides: dict[str, Any]
) -> None:
    body = new_source_body(**overrides)
    if "connector_config" not in overrides:
        body["connector_config"] = {"credential_ref": CONFIG_SECRET}

    response = api.post("/sources", body)

    assert response.status_code == 400
    assert BODY_SENTINEL not in response.text
    assert CONFIG_SECRET not in response.text


def test_a_400_for_an_update_never_contains_the_input_values(api: ApiEnv) -> None:
    api.jobs.seed_source()
    body = update_body(ttl=BODY_SENTINEL, connector_config={"credential_ref": CONFIG_SECRET})
    body["status"] = BODY_SENTINEL

    response = api.put(UPDATE, body)

    assert response.status_code == 400
    assert BODY_SENTINEL not in response.text
    assert CONFIG_SECRET not in response.text


def test_a_400_for_the_crawl_request_never_contains_the_input_values(api: ApiEnv) -> None:
    response = api.post(CRAWL, {"force_delete": BODY_SENTINEL})

    assert response.status_code == 400
    assert BODY_SENTINEL not in response.text


def test_a_400_for_a_malformed_json_never_echoes_the_body(api: ApiEnv) -> None:
    response = api.post("/sources", raw=b'{"connector_config": {"x": "' + BODY_SENTINEL.encode())

    assert response.status_code == 400
    assert BODY_SENTINEL not in response.text


# --- 本文の大きさの上限(crawler-api 3.2。CAPI-P-28。10 MiB) ---

MAX_BODY = 10 * 1024 * 1024


def _body_of_size(size: int) -> bytes:
    """ちょうど `size` バイトの、有効な JSON のオブジェクトの本文(`ttl` に空白で埋める)。"""
    head = b'{"force_delete": false}'
    return head + b" " * (size - len(head))


@pytest.mark.parametrize("path", ["/sources", UPDATE, CRAWL])
def test_a_body_over_the_limit_is_400_without_details_and_not_parsed(
    api: ApiEnv, path: str
) -> None:
    api.jobs.seed_source()

    response = api.client.request(
        "PUT" if path == UPDATE else "POST", path, content=_body_of_size(MAX_BODY + 1)
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert "details" not in response.json()["error"]


def test_a_body_exactly_at_the_limit_is_read_and_validated(api: ApiEnv) -> None:
    api.jobs.seed_source()

    response = api.post(CRAWL, raw=_body_of_size(MAX_BODY))

    assert response.status_code == 202, response.text


def test_a_body_over_the_limit_without_content_length_is_stopped_while_reading(
    api: ApiEnv,
) -> None:
    api.jobs.seed_source()
    chunk = b" " * (1024 * 1024)

    def chunks():  # ジェネレータ = チャンク転送(`Content-Length` なし)
        yield b'{"force_delete": false}'
        for _ in range(11):
            yield chunk

    response = api.client.post(CRAWL, content=chunks())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_a_body_over_the_limit_is_rejected_before_the_stored_record_is_touched(
    api: ApiEnv,
) -> None:
    api.jobs.seed_source()
    before = api.sources_repository.body_of(SOURCE_ID)

    response = api.put(UPDATE, raw=_body_of_size(MAX_BODY + 1))

    assert response.status_code == 400
    assert api.sources_repository.body_of(SOURCE_ID) == before
