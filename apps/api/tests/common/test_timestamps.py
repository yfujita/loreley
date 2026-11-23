from datetime import UTC, datetime, timedelta, timezone

import pytest

from loreley_api.common.timestamps import format_instant, parse_instant

JST = timezone(timedelta(hours=9))


def test_a_value_is_formatted_in_utc_with_milliseconds() -> None:
    value = datetime(2026, 11, 22, 10, 2, 3, 456_000, tzinfo=JST)

    assert format_instant(value) == "2026-11-22T01:02:03.456Z"


def test_microseconds_are_truncated_not_rounded() -> None:
    assert format_instant(datetime(2026, 1, 1, 0, 0, 0, 999_999, tzinfo=UTC)) == (
        "2026-01-01T00:00:00.999Z"
    )
    assert (
        format_instant(datetime(2026, 1, 1, 0, 0, 0, 0, tzinfo=UTC)) == "2026-01-01T00:00:00.000Z"
    )


def test_formatting_a_naive_value_fails() -> None:
    with pytest.raises(ValueError, match="timezone"):
        format_instant(datetime(2026, 1, 1))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-11-22T01:02:03.456Z", datetime(2026, 11, 22, 1, 2, 3, 456_000, tzinfo=UTC)),
        ("2026-11-22T10:02:03+09:00", datetime(2026, 11, 22, 1, 2, 3, tzinfo=UTC)),
        ("2026-11-22T01:02:03+00:00", datetime(2026, 11, 22, 1, 2, 3, tzinfo=UTC)),
    ],
)
def test_a_value_with_an_offset_is_read_as_utc(text: str, expected: datetime) -> None:
    value = parse_instant(text)

    assert value == expected
    assert value.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "text",
    [
        "2026-11-22T01:02:03",  # オフセットなし
        "SENTINEL-NOT-A-DATE",
        "",
        "2026-13-01T00:00:00Z",
        "9999-12-31T23:59:59-05:00",  # UTC にすると範囲を超える
    ],
)
def test_an_unreadable_value_fails_without_showing_it(text: str) -> None:
    with pytest.raises(ValueError) as error_info:
        parse_instant(text)

    assert "SENTINEL" not in str(error_info.value)
    assert text not in str(error_info.value) or text == ""
