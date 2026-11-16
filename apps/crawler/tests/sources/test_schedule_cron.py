"""`schedule_cron`(標準の 5 項目の cron 式)の検証と、次に合う時刻の計算。"""

from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from loreley_crawler.sources import schedule_cron
from loreley_crawler.sources.schedule_cron import (
    SCHEDULE_CRON_MAX_LENGTH,
    InvalidScheduleCron,
    is_valid_schedule_cron,
    next_fire_time,
)

TOKYO = ZoneInfo("Asia/Tokyo")
# 全角数字(ruff の曖昧文字の検査を避けるため、コードポイントから作る)。
FULLWIDTH_ZERO = chr(0xFF10)


# --- 検証 ---


@pytest.mark.parametrize(
    "expression",
    [
        "* * * * *",
        "0 3 * * *",
        "*/5 * * * *",
        "0,30 9-17 * * 1-5",
        "0 0 1 1 *",
        "0 0 29 2 *",  # 閏年にだけ合う(次の合う時刻は数年先)
        "0 3 * * MON",  # cronsim が受け付ける英語名(止めない)
        "0 3 L * *",
    ],
)
def test_a_five_field_expression_is_valid(expression: str) -> None:
    assert is_valid_schedule_cron(expression) is True


@pytest.mark.parametrize(
    "expression",
    [
        "",
        " ",
        "* * * *",  # 4 項目
        "0 0 3 * * *",  # 秒つきの 6 項目(cronsim は受け付けるが、標準の 5 項目に絞る)
        "@daily",
        "@hourly",
        "@daily * * * *",
        " 0 3 * * *",  # 前後の空白
        "0 3 * * * ",
        "0 3 * * *\n",
        "0  3 * * *",  # 区切りの空白が複数
        "0\t3 * * * *",
        "60 * * * *",
        "* 24 * * *",
        "* * 0 * *",
        "* * 32 * *",
        "* * * 13 *",
        "* * * * 8",
        "*/0 * * * *",
        "5-1 * * * *",
        "a b c d e",
        "0 0 30 2 *",  # 2 月 30 日は存在しない
        "0 0 31 4 *",
        "5 * */16 * 5#2",  # 合う時刻が探索の範囲にない(`StopIteration`)
        "\x00 * * * *",
        f"{FULLWIDTH_ZERO} * * * *",
        "0 3 * * *" + "," * SCHEDULE_CRON_MAX_LENGTH,  # 長さの上限超過
    ],
)
def test_anything_else_is_invalid(expression: str) -> None:
    assert is_valid_schedule_cron(expression) is False


def test_an_expression_of_exactly_the_maximum_length_is_judged_by_its_content() -> None:
    minutes = ",".join(str(minute) for minute in range(60))
    expression = f"{minutes} * * * *"
    padded = expression[:-1] + "*" * (SCHEDULE_CRON_MAX_LENGTH - len(expression) + 1)
    assert len(padded) == SCHEDULE_CRON_MAX_LENGTH

    assert is_valid_schedule_cron(expression) is True
    assert is_valid_schedule_cron(padded) is False  # 長さは上限内で、中身が不正
    assert is_valid_schedule_cron(padded + "*") is False  # 上限超過


def test_an_unexpected_library_error_is_an_invalid_expression_not_an_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(schedule_cron, "CronSim", explode)

    assert is_valid_schedule_cron("0 3 * * *") is False


# --- 次に合う時刻 ---


def test_the_first_matching_time_after_the_base_is_returned() -> None:
    base = datetime(2026, 11, 16, 1, 30, tzinfo=UTC)

    assert next_fire_time("0 3 * * *", after=base, zone=UTC) == datetime(
        2026, 11, 16, 3, 0, tzinfo=UTC
    )
    assert next_fire_time("*/15 * * * *", after=base, zone=UTC) == datetime(
        2026, 11, 16, 1, 45, tzinfo=UTC
    )


def test_a_base_exactly_on_a_matching_time_is_excluded() -> None:
    base = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)

    assert next_fire_time("0 3 * * *", after=base, zone=UTC) == datetime(
        2026, 11, 17, 3, 0, tzinfo=UTC
    )


def test_the_matching_time_is_the_next_minute_boundary_for_a_base_with_seconds() -> None:
    just_before = datetime(2026, 11, 16, 2, 59, 59, 999_000, tzinfo=UTC)
    just_after = datetime(2026, 11, 16, 3, 0, 0, 1_000, tzinfo=UTC)

    assert next_fire_time("0 3 * * *", after=just_before, zone=UTC) == datetime(
        2026, 11, 16, 3, 0, tzinfo=UTC
    )
    assert next_fire_time("0 3 * * *", after=just_after, zone=UTC) == datetime(
        2026, 11, 17, 3, 0, tzinfo=UTC
    )


def test_the_expression_is_read_in_the_given_time_zone() -> None:
    base = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)  # 東京の 09:00

    tokyo = next_fire_time("0 3 * * *", after=base, zone=TOKYO)
    utc = next_fire_time("0 3 * * *", after=base, zone=UTC)

    assert tokyo == datetime(2026, 11, 16, 18, 0, tzinfo=UTC)  # 東京の翌日 03:00
    assert tokyo.utcoffset() == timedelta(hours=9)
    assert utc == datetime(2026, 11, 16, 3, 0, tzinfo=UTC)


def test_the_day_of_the_month_follows_the_calendar_of_the_time_zone() -> None:
    base = datetime(2026, 11, 30, 16, 0, tzinfo=UTC)  # 東京ではもう 12 月 1 日 01:00

    assert next_fire_time("0 0 1 * *", after=base, zone=TOKYO) == datetime(
        2026, 12, 31, 15, 0, tzinfo=UTC
    )  # 東京の 1 月 1 日 00:00
    assert next_fire_time("0 0 1 * *", after=base, zone=UTC) == datetime(
        2026, 12, 1, 0, 0, tzinfo=UTC
    )


def test_a_fixed_offset_zone_is_accepted() -> None:
    base = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
    jst = timezone(timedelta(hours=9))

    assert next_fire_time("0 3 * * *", after=base, zone=jst) == datetime(
        2026, 11, 16, 18, 0, tzinfo=UTC
    )


@pytest.mark.parametrize("expression", ["* * * *", "0 0 3 * * *", "@daily", "60 * * * *", ""])
def test_an_invalid_expression_raises_without_echoing_it(expression: str) -> None:
    base = datetime(2026, 11, 16, tzinfo=UTC)

    with pytest.raises(InvalidScheduleCron) as raised:
        next_fire_time(expression, after=base, zone=UTC)

    assert expression not in str(raised.value) or expression == ""
    assert raised.value.__cause__ is None


def test_the_next_time_is_never_before_the_base_when_daylight_saving_ends() -> None:
    """夏時間が終わる日の 2 回ある時刻(America/New_York の 2026-11-01 01:30)。cronsim は 2 回目の
    時間帯の起点に、起点より前の瞬間(1 回目の 01:30 EDT)を返すことがある。"""
    new_york = ZoneInfo("America/New_York")
    base = datetime(2026, 11, 1, 4, 0, tzinfo=UTC)
    end = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
    while base < end:
        fire = next_fire_time("30 1 * * *", after=base, zone=new_york)
        assert fire.astimezone(UTC) > base
        base += timedelta(minutes=5)
    first = next_fire_time(
        "30 1 * * *", after=datetime(2026, 11, 1, 4, 0, tzinfo=UTC), zone=new_york
    )
    assert first.astimezone(UTC) == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)  # 1 回目(EDT)
    # 2 回目の時間帯の起点(06:10 UTC = 01:10 EST)の次は、翌日の 01:30 EST。
    second = next_fire_time(
        "30 1 * * *", after=datetime(2026, 11, 1, 6, 10, tzinfo=UTC), zone=new_york
    )
    assert second.astimezone(UTC) == datetime(2026, 11, 2, 6, 30, tzinfo=UTC)


def test_an_expression_over_the_length_limit_is_not_given_to_the_library(monkeypatch) -> None:
    called = []
    monkeypatch.setattr(schedule_cron, "CronSim", lambda *args, **kwargs: called.append(1))

    with pytest.raises(InvalidScheduleCron):
        next_fire_time(
            "0 3 * * *" + "," * SCHEDULE_CRON_MAX_LENGTH,
            after=datetime(2026, 1, 1, tzinfo=UTC),
            zone=UTC,
        )

    assert called == []
