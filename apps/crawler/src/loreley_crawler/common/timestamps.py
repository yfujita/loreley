"""日時の書式。

Crawler が保存・送信する日時は、UTC・ISO 8601・ミリ秒精度
(例: `2026-11-13T01:02:03.456Z`)の文字列で書く(architecture 2.5。CA-P-38)。
Indexer が同じ形式に正規化して扱うため、揃えておくと比較でずれない。
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
    """`format_instant` が書いた形式(タイムゾーン付きの ISO 8601)を、UTC の aware な値に読み戻す。

    タイムゾーンのない値・日時として読めない値は `ValueError`。どう扱うか(ロックのリースなら
    「所有していない」側)は呼び出し側が決める。
    """
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone offset")
    try:
        return value.astimezone(UTC)
    except OverflowError:
        # `9999-12-31T23:59:59-05:00` などは、UTC にすると範囲を超える。呼び出し側は
        # `ValueError` だけを「読めない値」として扱うので、値を載せずに変換する。
        raise ValueError("timestamp is out of range") from None
