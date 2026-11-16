"""値の規則の検証関数(crawler-api 4.4.1)と、`reason` の対応。"""

import math

import pytest

from loreley_crawler.connectors.interface import ConnectorError, ErrorCategory
from loreley_crawler.sources import (
    ProblemReason,
    ValueProblem,
    check_connector_config_is_object,
    check_connector_type,
    check_integer,
    check_ratio_threshold,
    check_schedule_cron,
    check_source_id,
    validate_connector_config,
    validate_source_values,
)
from tests.fakes.fake_connector import VALIDATE_CONFIG, FakeConnectorType
from tests.sources.support import make_registry

TYPE = ProblemReason.TYPE
# 全角英数字(ruff の曖昧文字の検査を避けるため、コードポイントから作る)。
FULLWIDTH_ABC = "".join(chr(code) for code in (0xFF41, 0xFF42, 0xFF43))
FORMAT = ProblemReason.FORMAT


# --- source_id(確定: 空でない・制御文字なし・256 バイト以内。案 CAPI-P-15: 文字種) ---


@pytest.mark.parametrize(
    "source_id",
    ["a", "docs", "Docs-1", "a.b_c-d", "0abc", "a" * 256, "a..b", "a-", "A"],
)
def test_valid_source_ids_pass(source_id: str) -> None:
    assert check_source_id(source_id) is None


@pytest.mark.parametrize(
    "source_id",
    [
        "",  # 空
        "-a",  # 英数字で始まらない
        ".a",
        "_a",
        "a/b",  # パスに入れられない文字
        "a%2Fb",
        "a?b",
        "a#b",
        "a b",
        "a\nb",  # 制御文字
        "a\n",  # 末尾の改行(`$` の取り違えを避ける)
        "\x00",
        "日本語",  # 半角英数字以外
        FULLWIDTH_ABC,
        "é",
        "a" * 257,  # 256 を超える
    ],
)
def test_invalid_source_ids_are_format_violations(source_id: str) -> None:
    assert check_source_id(source_id) == ValueProblem("source_id", FORMAT)


@pytest.mark.parametrize("value", [None, 1, 1.5, True, ["a"], {"a": 1}])
def test_a_non_string_source_id_is_a_type_violation(value: object) -> None:
    assert check_source_id(value) == ValueProblem("source_id", TYPE)


# --- ttl・min_delete_count(整数。範囲は見ない) ---


@pytest.mark.parametrize("value", [0, 1, -5, 2_592_000, 10**30])
def test_integers_pass_without_a_range_check(value: int) -> None:
    assert check_integer("ttl", value) is None
    assert check_integer("min_delete_count", value) is None


@pytest.mark.parametrize("value", [1.0, 1.5, "1", None, True, False, [1], math.nan])
def test_non_integers_are_type_violations_naming_the_field(value: object) -> None:
    assert check_integer("ttl", value) == ValueProblem("ttl", TYPE)
    assert check_integer("min_delete_count", value) == ValueProblem("min_delete_count", TYPE)


# --- ratio_threshold(有限の数。範囲は見ない) ---


@pytest.mark.parametrize("value", [0, 1, 0.3, 1.0, 2.5, -1, 100, 10**400, 1e308])
def test_finite_numbers_pass_without_a_range_check(value: float) -> None:
    assert check_ratio_threshold(value) is None


@pytest.mark.parametrize(
    "value", [math.nan, math.inf, -math.inf, "0.3", None, True, False, [0.3], {"v": 1}]
)
def test_non_finite_or_non_numbers_are_type_violations(value: object) -> None:
    assert check_ratio_threshold(value) == ValueProblem("ratio_threshold", TYPE)


# --- schedule_cron(標準の 5 項目の cron 式、または null) ---


@pytest.mark.parametrize("value", [None, "* * * * *", "0 3 * * *", "*/15 9-17 * * 1-5"])
def test_valid_schedule_crons_pass(value: str | None) -> None:
    assert check_schedule_cron(value) is None


@pytest.mark.parametrize(
    "value",
    ["", "   ", "0 3 * *", "0 0 3 * * *", "@daily", "60 3 * * *", "0 3 * * 8", "a b c d e"],
)
def test_a_string_that_is_not_a_five_field_cron_is_a_format_violation(value: str) -> None:
    assert check_schedule_cron(value) == ValueProblem("schedule_cron", FORMAT)


@pytest.mark.parametrize("value", [3600, 1.5, True, False, ["0 3 * * *"], {"a": 1}])
def test_a_non_string_schedule_cron_is_a_type_violation(value: object) -> None:
    assert check_schedule_cron(value) == ValueProblem("schedule_cron", TYPE)


# --- connector_type(登録済み) ---


def test_a_registered_connector_type_passes() -> None:
    assert check_connector_type("file_system", make_registry()) is None


@pytest.mark.parametrize("value", ["web", "File_System", "", "file_system "])
def test_an_unregistered_connector_type_is_unsupported(value: str) -> None:
    assert check_connector_type(value, make_registry()) == ValueProblem(
        "connector_type", ProblemReason.UNSUPPORTED
    )


@pytest.mark.parametrize("value", [None, 1, ["file_system"]])
def test_a_non_string_connector_type_is_a_type_violation(value: object) -> None:
    assert check_connector_type(value, make_registry()) == ValueProblem("connector_type", TYPE)


@pytest.mark.parametrize("value", [{}, {"root": "/x"}])
def test_a_json_object_passes_the_connector_config_shape_check(value: object) -> None:
    assert check_connector_config_is_object(value) is None


@pytest.mark.parametrize("value", [None, "x", 1, [], [{"a": 1}]])
def test_a_connector_config_that_is_not_an_object_is_a_type_violation(value: object) -> None:
    assert check_connector_config_is_object(value) == ValueProblem("connector_config", TYPE)


# --- まとめて検査 ---


def test_validate_source_values_reports_every_violation_in_a_fixed_order() -> None:
    problems = validate_source_values(
        {
            "schedule_cron": "* * * *",
            "min_delete_count": "10",
            "ratio_threshold": math.nan,
            "ttl": 1.5,
            "connector_config": [],
            "connector_type": "web",
            "source_id": "a/b",
        },
        make_registry(),
    )

    assert problems == [
        ValueProblem("source_id", FORMAT),
        ValueProblem("connector_type", ProblemReason.UNSUPPORTED),
        ValueProblem("connector_config", TYPE),
        ValueProblem("ttl", TYPE),
        ValueProblem("ratio_threshold", TYPE),
        ValueProblem("min_delete_count", TYPE),
        ValueProblem("schedule_cron", FORMAT),
    ]


def test_validate_source_values_checks_only_the_given_fields() -> None:
    # 更新の本文には `source_id`・`connector_type` がない。必須の確認は `api` が行う。
    assert validate_source_values({"ttl": 10}, make_registry()) == []
    assert validate_source_values({"ttl": "10"}, make_registry()) == [ValueProblem("ttl", TYPE)]
    assert validate_source_values({}, make_registry()) == []


def test_validate_source_values_accepts_a_valid_registration() -> None:
    values = {
        "source_id": "docs",
        "connector_type": "file_system",
        "connector_config": {"root": "/data"},
        "ttl": 2_592_000,
        "ratio_threshold": 0.3,
        "min_delete_count": 10,
        "schedule_cron": None,
    }
    assert validate_source_values(values, make_registry()) == []


# --- validate_config の確認 ---


def test_validate_connector_config_passes_the_config_to_the_connector_type() -> None:
    connector_type = FakeConnectorType()
    config = {"root": "/data"}

    validate_connector_config(make_registry(connector_type), "file_system", config)

    assert connector_type.validated_configs == [config]


def test_a_config_violation_is_raised_as_config_invalid() -> None:
    connector_type = FakeConnectorType()
    violation = ConnectorError.of(ErrorCategory.CONFIG_INVALID, "root is required")
    connector_type.behavior.inject(VALIDATE_CONFIG, violation)

    with pytest.raises(ConnectorError) as raised:
        validate_connector_config(make_registry(connector_type), "file_system", {})

    assert raised.value.category is ErrorCategory.CONFIG_INVALID
    assert raised.value.message == "root is required"


def test_an_unexpected_exception_is_converted_to_connector_internal_error() -> None:
    connector_type = FakeConnectorType()
    connector_type.behavior.inject(VALIDATE_CONFIG, RuntimeError("SECRET-detail"))

    with pytest.raises(ConnectorError) as raised:
        validate_connector_config(make_registry(connector_type), "file_system", {})

    assert raised.value.category is ErrorCategory.CONNECTOR_INTERNAL_ERROR
    assert "SECRET-detail" not in raised.value.message


def test_validating_the_config_of_an_unregistered_type_is_a_caller_error() -> None:
    with pytest.raises(ValueError):
        validate_connector_config(make_registry(), "web", {})
