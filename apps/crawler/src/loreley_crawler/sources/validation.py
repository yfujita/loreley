"""データソース設定の値の規則と、その検証関数(module 4.3。crawler-api 3.2・4.4.1)。

`api` が、JSON の形式の検証(必須・未知の項目・読み取り専用・厳密な型への変換禁止)の後に、
ここの関数を呼び、返された `reason` をそのままエラー応答の `details.errors` に使う。ここは
「値の規則そのもの」だけを持ち、JSON の形式と応答は持たない。しきい値の範囲(`ratio_threshold` が
0 以上 1 未満など)は見ない(Admin API の領域。CA-K-16)。

案に依存する規則(`source_id` の文字種 = CAPI-P-15)は、このファイルの定数 1 か所に置く。
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from loreley_crawler.connectors.registry import ConnectorRegistry
from loreley_crawler.sources.schedule_cron import is_valid_schedule_cron

# 確定(CAPI-K-6): 空でない・制御文字を含まない・UTF-8 で 256 バイト以内。
# 案(CAPI-P-15。最終決定は CAPI-U-4): 半角英数字で始まり、半角英数字・`.`・`_`・`-` だけ。
# 文字種を案の ASCII に絞ると、空・制御文字・`/`・`%`・`?`・`#` は必ず弾かれ、文字数と
# UTF-8 のバイト数が一致する。文字種を緩める改版では、制御文字とバイト数の検査をここに足すこと。
SOURCE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
SOURCE_ID_MAX_LENGTH = 256


class ProblemReason(StrEnum):
    """crawler-api 3.3 の `reason` のうち、値の規則の違反で `sources` が返すもの。

    `required`・`read_only`・`unknown_field` は JSON の形式の違反で、`api` が決める。
    """

    TYPE = "type"
    FORMAT = "format"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ValueProblem:
    field: str
    reason: ProblemReason


def check_source_id(value: object) -> ValueProblem | None:
    if not isinstance(value, str):
        return ValueProblem("source_id", ProblemReason.TYPE)
    if SOURCE_ID_PATTERN.fullmatch(value) is None or len(value) > SOURCE_ID_MAX_LENGTH:
        return ValueProblem("source_id", ProblemReason.FORMAT)
    return None


def check_connector_type(value: object, registry: ConnectorRegistry) -> ValueProblem | None:
    if not isinstance(value, str):
        return ValueProblem("connector_type", ProblemReason.TYPE)
    if registry.find(value) is None:
        return ValueProblem("connector_type", ProblemReason.UNSUPPORTED)
    return None


def check_connector_config_is_object(value: object) -> ValueProblem | None:
    """`connector_config` の中身は Connector が見る。ここは JSON のオブジェクトかだけ。"""
    if not isinstance(value, dict):
        return ValueProblem("connector_config", ProblemReason.TYPE)
    return None


def check_integer(field: str, value: object) -> ValueProblem | None:
    """`ttl`・`min_delete_count`。整数であること(範囲は見ない)。`bool` と小数は整数ではない。"""
    if type(value) is not int:
        return ValueProblem(field, ProblemReason.TYPE)
    return None


def check_ratio_threshold(value: object) -> ValueProblem | None:
    """有限の数であること(範囲は見ない)。`bool`・文字列・`NaN`・`Infinity` は型の違反。"""
    if type(value) is int:
        return None
    if type(value) is float and isfinite(value):
        return None
    return ValueProblem("ratio_threshold", ProblemReason.TYPE)


def check_schedule_cron(value: object) -> ValueProblem | None:
    """標準の 5 項目の cron 式(文字列)、または null(手動のみ)。"""
    if value is None:
        return None
    if not isinstance(value, str):
        return ValueProblem("schedule_cron", ProblemReason.TYPE)
    if not is_valid_schedule_cron(value):
        return ValueProblem("schedule_cron", ProblemReason.FORMAT)
    return None


def validate_source_values(
    values: Mapping[str, object], registry: ConnectorRegistry
) -> list[ValueProblem]:
    """渡された項目の値の規則を、項目の順(固定)に検査する。ない項目は検査しない。

    必須の項目の有無(`required`)は `api` が見る。
    """
    checks = (
        ("source_id", check_source_id),
        ("connector_type", lambda value: check_connector_type(value, registry)),
        ("connector_config", check_connector_config_is_object),
        ("ttl", lambda value: check_integer("ttl", value)),
        ("ratio_threshold", check_ratio_threshold),
        ("min_delete_count", lambda value: check_integer("min_delete_count", value)),
        ("schedule_cron", check_schedule_cron),
    )
    problems = (check(values[field]) for field, check in checks if field in values)
    return [problem for problem in problems if problem is not None]


def validate_connector_config(
    registry: ConnectorRegistry, connector_type: str, connector_config: object
) -> None:
    """`ConnectorType.validate_config` で `connector_config` を確認する(I/O なし)。

    違反は `ConnectorError`(`config_invalid`)、想定外の例外はレジストリの保護ラッパが変換した
    `ConnectorError`(`connector_internal_error`)として送出される(`api` が 400・500 にする)。
    `connector_type` が登録済みであることは、先に `check_connector_type` で確かめておくこと。
    """
    registered = registry.find(connector_type)
    if registered is None:
        raise ValueError("connector_type is not registered")
    registered.validate_config(connector_config)
