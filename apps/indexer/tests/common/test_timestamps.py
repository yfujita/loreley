from datetime import UTC, datetime, timedelta, timezone

import pytest

from loreley_indexer.common.timestamps import format_instant, normalize_instant, parse_instant


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-11-09T01:00:00.000Z", "2026-11-09T01:00:00.000Z"),
        ("2026-11-09T01:00:00Z", "2026-11-09T01:00:00.000Z"),  # 秒精度
        ("2026-11-09T10:00:00+09:00", "2026-11-09T01:00:00.000Z"),  # オフセット付き
        ("2026-11-09T01:00:00.123456Z", "2026-11-09T01:00:00.123Z"),  # マイクロ秒は切り捨て
        ("2026-11-09T01:00:00.9999Z", "2026-11-09T01:00:00.999Z"),
    ],
)
def test_normalize_instant_converts_to_utc_milliseconds(raw: str, expected: str) -> None:
    assert normalize_instant(raw) == expected


def test_normalized_strings_sort_in_time_order() -> None:
    earlier = normalize_instant("2026-11-09T01:00:00Z")
    later = normalize_instant("2026-11-09T10:30:00+09:00")  # 01:30Z
    assert earlier < later


@pytest.mark.parametrize("raw", ["2026-11-09T01:00:00", "2026-11-09", "not-a-date", ""])
def test_parse_instant_rejects_values_without_timezone_or_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_instant(raw)


def test_parse_instant_error_does_not_echo_input() -> None:
    with pytest.raises(ValueError) as excinfo:
        parse_instant("secret-looking-input")
    assert "secret-looking-input" not in str(excinfo.value)


def test_format_instant_converts_aware_datetime_to_utc() -> None:
    jst = timezone(timedelta(hours=9))
    assert format_instant(datetime(2026, 11, 9, 10, 0, 0, 5000, tzinfo=jst)) == (
        "2026-11-09T01:00:00.005Z"
    )


def test_format_instant_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        format_instant(datetime(2026, 11, 9, 1, 0, 0))


def test_parse_instant_returns_utc() -> None:
    assert parse_instant("2026-11-09T10:00:00+09:00") == datetime(2026, 11, 9, 1, tzinfo=UTC)
