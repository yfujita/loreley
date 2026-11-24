"""読めない値の扱い(C 5.0)。

Crawler・Indexer が書いた値は、型が違えば「読めない値」で、その項目を `None`(応答では `null`)に
する。ここの関数は、読めたら値を、読めなければ `None` を返す。例外は出さない。
"""

import math
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum

from loreley_api.common.timestamps import format_instant, parse_instant

type Document = Mapping[str, object]


def read_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def read_non_empty_str(value: object) -> str | None:
    return value if isinstance(value, str) and value != "" else None


def read_int(value: object) -> int | None:
    """`bool` を除く整数(`bool` は `int` の子だが、真偽値であって件数ではない)。"""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def read_number(value: object) -> int | float | None:
    """`bool` を除く、有限の整数または浮動小数。"""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def read_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def read_mapping(value: object) -> Document | None:
    return value if isinstance(value, Mapping) else None


def read_instant(value: object) -> datetime | None:
    """タイムゾーン付きの ISO 8601 だけ。読めない日時・UTC にして範囲を超える値は `None`。"""
    if not isinstance(value, str):
        return None
    try:
        return parse_instant(value)
    except ValueError:
        return None


def read_instant_text(value: object) -> str | None:
    """読める日時を、UTC ミリ秒の文字列にする(応答用)。"""
    instant = read_instant(value)
    return format_instant(instant) if instant is not None else None


def read_choice[E: StrEnum](value: object, choices: type[E]) -> E | None:
    """`choices` のどれかの値なら、その列挙値。

    許される値にない値は読めない値として `None`(未知の値を通さない)。
    """
    if not isinstance(value, str):
        return None
    try:
        return choices(value)
    except ValueError:
        return None
