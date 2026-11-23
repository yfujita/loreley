"""日時の読み取りと整形(C 5.0。A 5.1)。

API が返す日時は、UTC・ISO 8601・ミリ秒精度(例 `2026-11-22T01:02:03.456Z`)の文字列。
Crawler・Indexer が保存した日時は、タイムゾーン(`Z` またはオフセット)を持つものだけを読める。
オフセットのない値・日時として読めない値・UTC にすると範囲を超える値は「読めない日時」で、
どう扱うか(その項目を `null` にするなど)は呼び出し側が決める。
"""

from datetime import UTC, datetime


def format_instant(value: datetime) -> str:
    """aware な datetime を、UTC・ミリ秒精度(切り捨て)の文字列にする。"""
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone offset")
    utc_value = value.astimezone(UTC)
    millis = utc_value.microsecond // 1000
    return f"{utc_value:%Y-%m-%dT%H:%M:%S}.{millis:03d}Z"


def parse_instant(text: str) -> datetime:
    """タイムゾーン付きの ISO 8601 を、UTC の aware な値に読む。

    読めない日時は `ValueError`(メッセージに値を含めない)。
    """
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        # 標準ライブラリのメッセージは入力値を含むので、固定文に置き換える。
        raise ValueError("timestamp is not a valid ISO 8601 datetime") from None
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone offset")
    try:
        return value.astimezone(UTC)
    except OverflowError:
        # `9999-12-31T23:59:59-05:00` などは、UTC にすると範囲を超える。
        raise ValueError("timestamp is out of range") from None
