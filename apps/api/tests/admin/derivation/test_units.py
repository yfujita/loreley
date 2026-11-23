"""TTL・しきい値の変換(C 5.7。C 11章 5)。"""

import math

import pytest

from loreley_api.admin.base.codes import Reason
from loreley_api.admin.derivation.units import (
    INT64_MAX,
    InvalidValue,
    percent_to_ratio,
    ratio_to_percent,
    ttl_days_to_seconds,
    ttl_seconds_to_days,
    validate_min_delete_count,
    validate_ttl_seconds,
)

RANGE = InvalidValue(Reason.RANGE)
FORMAT = InvalidValue(Reason.FORMAT)


@pytest.mark.parametrize(
    ("percent", "ratio"),
    [
        (0.29, 0.0029),
        (0.1, 0.001),
        (20, 0.2),
        (20.0, 0.2),
        (99.99, 0.9999),
        (0, 0.0),
        (0.01, 0.0001),
        (1e1, 0.1),
    ],
)
def test_a_percent_is_converted_to_a_ratio_without_float_error(
    percent: float, ratio: float
) -> None:
    assert percent_to_ratio(percent) == ratio


@pytest.mark.parametrize(
    ("percent", "expected"),
    [
        (100, RANGE),
        (100.0, RANGE),
        (-0.01, RANGE),
        (-1, RANGE),
        (150.123, RANGE),
        (math.inf, RANGE),
        (math.nan, RANGE),
        (12.345, FORMAT),
        (1e-3, FORMAT),
        (0.001, FORMAT),
        (99.999, FORMAT),
    ],
)
def test_a_percent_out_of_range_or_with_a_third_decimal_place_is_invalid(
    percent: float, expected: InvalidValue
) -> None:
    assert percent_to_ratio(percent) == expected


@pytest.mark.parametrize(
    ("ratio", "percent"),
    [
        (0.29, 29),
        (0.2, 20),
        (0.1, 10),
        (0.0029, 0.29),
        (0, 0),
        (1, 100),
        (0.12345, 12.345),
        (1e-3, 0.1),
    ],
)
def test_a_ratio_is_converted_to_a_percent_exactly(ratio: float, percent: float) -> None:
    result = ratio_to_percent(ratio)

    assert result == percent
    # 整数値になるときは整数で返す(`20.0` ではなく `20`)。
    assert isinstance(result, int) == (percent == int(percent))


def test_a_ratio_that_is_not_finite_is_not_converted() -> None:
    assert ratio_to_percent(math.inf) is None
    assert ratio_to_percent(math.nan) is None


@pytest.mark.parametrize(("days", "seconds"), [(1, 86_400), (30, 2_592_000)])
def test_ttl_days_are_converted_to_seconds(days: int, seconds: int) -> None:
    assert ttl_days_to_seconds(days) == seconds


@pytest.mark.parametrize("days", [0, -1, INT64_MAX // 86_400 + 1, INT64_MAX])
def test_ttl_days_must_be_positive_and_fit_in_int64_as_seconds(days: int) -> None:
    assert ttl_days_to_seconds(days) == RANGE


def test_the_largest_ttl_days_that_fit_in_int64_are_accepted() -> None:
    days = INT64_MAX // 86_400

    assert ttl_days_to_seconds(days) == days * 86_400


@pytest.mark.parametrize(("seconds", "expected"), [(1, 1), (INT64_MAX, INT64_MAX)])
def test_ttl_seconds_inside_the_bounds_are_accepted(seconds: int, expected: int) -> None:
    assert validate_ttl_seconds(seconds) == expected


@pytest.mark.parametrize("seconds", [0, -1, INT64_MAX + 1])
def test_ttl_seconds_outside_the_bounds_are_invalid(seconds: int) -> None:
    assert validate_ttl_seconds(seconds) == RANGE


@pytest.mark.parametrize("count", [0, 1, INT64_MAX])
def test_min_delete_count_inside_the_bounds_is_accepted(count: int) -> None:
    assert validate_min_delete_count(count) == count


@pytest.mark.parametrize("count", [-1, INT64_MAX + 1])
def test_min_delete_count_outside_the_bounds_is_invalid(count: int) -> None:
    assert validate_min_delete_count(count) == RANGE


@pytest.mark.parametrize(
    ("seconds", "days"), [(86_400, 1), (2_592_000, 30), (86_401, None), (90, None), (0, 0)]
)
def test_ttl_days_are_returned_only_when_the_seconds_divide_by_a_day(
    seconds: int, days: int | None
) -> None:
    assert ttl_seconds_to_days(seconds) == days
