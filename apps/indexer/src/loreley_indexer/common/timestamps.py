"""日時の正規化。

検索インデックスと `loreley-deletions` には、UTC・ISO 8601・ミリ秒精度
(例: `2026-11-09T01:00:00.000Z`)の文字列で保存する(arch 3.3、api 3.6)。
"""

from datetime import UTC, datetime


def parse_instant(value: str) -> datetime:
    """ISO 8601 文字列をタイムゾーン付き(UTC)の datetime にする。

    オフセットのない日時は時刻が定まらないため拒否する。
    例外メッセージには入力値を含めない(400 応答やログに入力値を出さないため)。
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("not an ISO 8601 timestamp") from None
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone offset")
    return parsed.astimezone(UTC)


def format_instant(value: datetime) -> str:
    """aware な datetime を、UTC・ミリ秒精度(切り捨て)の文字列にする。"""
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone offset")
    utc_value = value.astimezone(UTC)
    millis = utc_value.microsecond // 1000
    return f"{utc_value:%Y-%m-%dT%H:%M:%S}.{millis:03d}Z"


def normalize_instant(value: str) -> str:
    return format_instant(parse_instant(value))
