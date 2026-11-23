"""TTL・しきい値の変換(C 5.7。B 2.8)。

十進数(`Decimal`)で計算し、浮動小数の誤差を出さない(`0.29` → `29`。浮動小数なら
`28.999999999999996` になるところ)。`repr(float)` は 15 桁以内の十進表記なら入力どおりの十進表記に
戻る(最短表現)ので、画面で打ち込んだ値がそのまま扱われる。
"""

import math
from dataclasses import dataclass
from decimal import Decimal

from loreley_api.admin.base.codes import Reason

SECONDS_PER_DAY = 86_400
INT64_MAX = 2**63 - 1
# しきい値(%)は 0 以上 100 未満で、小数第 2 位まで(B 2.4)。
PERCENT_UPPER_BOUND = Decimal(100)
MAX_PERCENT_DECIMAL_PLACES = 2


@dataclass(frozen=True)
class InvalidValue:
    """要求の値の違反。`reason` は `range` または `format`(B 2.4)。"""

    reason: Reason


def _to_decimal(value: int | float) -> Decimal:
    return Decimal(repr(value)) if isinstance(value, float) else Decimal(value)


def percent_to_ratio(percent: int | float) -> float | InvalidValue:
    """要求の `ratio_threshold_percent`(%)を、Crawler の割合(0〜1)にする。

    範囲は 0 以上 100 未満(`range`)、小数第 3 位以下があれば `format`。範囲の違反を先に返す。
    `bool` は呼び出し側が型の検証で除いている。
    """
    if isinstance(percent, float) and not math.isfinite(percent):
        return InvalidValue(Reason.RANGE)
    decimal = _to_decimal(percent)
    if not Decimal(0) <= decimal < PERCENT_UPPER_BOUND:
        return InvalidValue(Reason.RANGE)
    exponent = decimal.normalize().as_tuple().exponent
    if isinstance(exponent, int) and exponent < -MAX_PERCENT_DECIMAL_PLACES:
        return InvalidValue(Reason.FORMAT)
    return float(decimal / 100)


def ratio_to_percent(ratio: int | float) -> int | float | None:
    """保存値の割合(0〜1)を、応答の `ratio_threshold_percent`(%)にする。

    整数値になるときは整数で返す(`0.2` → `20`)。保存値が小数第 3 位以下を持てば、結果も小数第 2 位を
    超える(そのまま返す。B 2.8)。JSON にできない値(無限大)になるときは `None`。
    """
    if isinstance(ratio, float) and not math.isfinite(ratio):
        return None
    percent = _to_decimal(ratio) * 100
    if percent == percent.to_integral_value():
        return int(percent)
    result = float(percent)
    return result if math.isfinite(result) else None


def ttl_days_to_seconds(days: int) -> int | InvalidValue:
    """要求の `ttl_days` を秒にする。1 以上で、秒が int64 に収まること(`range`)。"""
    if days < 1 or days * SECONDS_PER_DAY > INT64_MAX:
        return InvalidValue(Reason.RANGE)
    return days * SECONDS_PER_DAY


def validate_ttl_seconds(seconds: int) -> int | InvalidValue:
    """要求の `ttl_seconds`。1 以上で int64 に収まること(`range`)。"""
    if seconds < 1 or seconds > INT64_MAX:
        return InvalidValue(Reason.RANGE)
    return seconds


def validate_min_delete_count(count: int) -> int | InvalidValue:
    """要求の `min_delete_count`。0 以上で int64 に収まること(`range`)。"""
    if count < 0 or count > INT64_MAX:
        return InvalidValue(Reason.RANGE)
    return count


def ttl_seconds_to_days(seconds: int) -> int | None:
    """応答の `ttl_days`。日で割り切れるときだけ整数、それ以外は `None`。"""
    return seconds // SECONDS_PER_DAY if seconds % SECONDS_PER_DAY == 0 else None
