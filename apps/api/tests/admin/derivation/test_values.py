"""読めない値の扱い(C 5.0)。"""

import math
from datetime import UTC, datetime
from enum import StrEnum

import pytest

from loreley_api.admin.derivation.values import (
    read_bool,
    read_choice,
    read_instant,
    read_instant_text,
    read_int,
    read_mapping,
    read_non_empty_str,
    read_number,
    read_str,
)


class Color(StrEnum):
    RED = "red"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, 0), (-3, -3), (True, None), (False, None), (1.0, None), ("1", None), (None, None)],
)
def test_an_integer_is_read_but_a_bool_is_not(value: object, expected: int | None) -> None:
    assert read_int(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, 1),
        (0.5, 0.5),
        (True, None),
        (math.inf, None),
        (-math.inf, None),
        (math.nan, None),
        ("0.5", None),
        (None, None),
    ],
)
def test_a_number_is_a_finite_int_or_float_but_not_a_bool(
    value: object, expected: float | None
) -> None:
    assert read_number(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"), [(True, True), (False, False), (1, None), ("true", None)]
)
def test_a_bool_is_read_only_from_a_bool(value: object, expected: bool | None) -> None:
    assert read_bool(value) is expected


def test_strings_and_mappings_are_read_only_from_the_same_type() -> None:
    assert read_str("") == ""
    assert read_str(1) is None
    assert read_non_empty_str("") is None
    assert read_non_empty_str("a") == "a"
    assert read_mapping({"a": 1}) == {"a": 1}
    assert read_mapping([("a", 1)]) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-11-22T01:02:03.456Z", datetime(2026, 11, 22, 1, 2, 3, 456000, tzinfo=UTC)),
        ("2026-11-22T10:02:03+09:00", datetime(2026, 11, 22, 1, 2, 3, tzinfo=UTC)),
        # オフセットのない値・日時として読めない値・型違い・UTC にして範囲を超える値は読めない。
        ("2026-11-22T01:02:03", None),
        ("2026-11-22", None),
        ("not a date", None),
        ("9999-12-31T23:59:59-05:00", None),
        (1_700_000_000, None),
        (None, None),
    ],
)
def test_an_instant_needs_a_timezone(value: object, expected: datetime | None) -> None:
    assert read_instant(value) == expected


def test_an_instant_text_is_utc_in_milliseconds_truncated() -> None:
    assert read_instant_text("2026-11-22T10:02:03.456789+09:00") == "2026-11-22T01:02:03.456Z"
    assert read_instant_text("garbage") is None


def test_a_choice_outside_the_allowed_values_is_not_passed_through() -> None:
    assert read_choice("red", Color) is Color.RED
    assert read_choice("blue", Color) is None
    assert read_choice(1, Color) is None
    assert read_choice(None, Color) is None
