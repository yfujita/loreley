from datetime import UTC, datetime, timedelta, timezone

import pytest

from loreley_crawler.common.timestamps import format_instant, parse_instant


def test_format_instant_writes_utc_milliseconds_with_z() -> None:
    value = datetime(2026, 11, 13, 1, 2, 3, 456000, tzinfo=UTC)
    assert format_instant(value) == "2026-11-13T01:02:03.456Z"


def test_format_instant_pads_zero_milliseconds() -> None:
    assert format_instant(datetime(2026, 11, 13, 1, 2, 3, tzinfo=UTC)) == "2026-11-13T01:02:03.000Z"
    assert (
        format_instant(datetime(2026, 11, 13, 1, 2, 3, 5000, tzinfo=UTC))
        == "2026-11-13T01:02:03.005Z"
    )


def test_format_instant_truncates_microseconds() -> None:
    assert (
        format_instant(datetime(2026, 11, 13, 1, 2, 3, 999999, tzinfo=UTC))
        == "2026-11-13T01:02:03.999Z"
    )


def test_format_instant_converts_other_offsets_to_utc() -> None:
    jst = timezone(timedelta(hours=9))
    assert (
        format_instant(datetime(2026, 11, 13, 10, 0, 0, 5000, tzinfo=jst))
        == "2026-11-13T01:00:00.005Z"
    )


def test_format_instant_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone"):
        format_instant(datetime(2026, 11, 13, 1, 0, 0))


def test_formatted_strings_sort_in_time_order() -> None:
    earlier = format_instant(datetime(2026, 11, 13, 1, 0, 0, 999000, tzinfo=UTC))
    later = format_instant(datetime(2026, 11, 13, 1, 0, 1, tzinfo=UTC))
    assert earlier < later


def test_parse_instant_reads_back_what_format_instant_wrote() -> None:
    value = datetime(2026, 11, 13, 1, 2, 3, 456000, tzinfo=UTC)
    assert parse_instant(format_instant(value)) == value


def test_parse_instant_converts_other_offsets_to_utc() -> None:
    parsed = parse_instant("2026-11-13T10:00:00.005+09:00")
    assert parsed == datetime(2026, 11, 13, 1, 0, 0, 5000, tzinfo=UTC)
    assert parsed.utcoffset() == timedelta(0)


@pytest.mark.parametrize("text", ["9999-12-31T23:59:59-05:00", "0001-01-01T00:00:00+09:00"])
def test_parse_instant_turns_a_utc_overflow_into_a_value_error_without_the_input(
    text: str,
) -> None:
    """UTC にすると範囲を超える値は `OverflowError` になるが、呼び出し側は `ValueError` だけを
    「読めない値」として扱う。"""
    with pytest.raises(ValueError) as raised:
        parse_instant(text)

    assert text not in str(raised.value)
    assert raised.value.__suppress_context__ is True


@pytest.mark.parametrize("text", ["2026-11-13T01:02:03.456", "2026-11-13", "", "not a date", "x"])
def test_parse_instant_rejects_values_without_a_timezone_or_unreadable_values(text: str) -> None:
    with pytest.raises(ValueError):
        parse_instant(text)
