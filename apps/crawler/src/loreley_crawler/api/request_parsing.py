"""リクエストの形式の検証(crawler-api 3.2・4.1・4.4)。形式と受け渡しだけで、業務判断はしない(R4)。

- **JSON は厳密に扱う**: 数値・真偽値を文字列などから変換しない。`NaN`・`Infinity`・`1e999` のような
  有限でない数値は、`connector_config` の中も含めて `type` の違反にする。
- 必須の項目(`required`)・未知の項目(`unknown_field`)・読み取り専用の項目(`read_only`)は、
  ここで決める。**値の規則そのもの**(`source_id` の文字種、`ttl` が整数など)は `sources` が持ち、
  その検証関数の結果を `reason` にそのまま使う(`sources.ProblemReason`)。
- 違反は `InvalidRequestError` で、項目名と `reason` だけを持つ。入力の値は含めない(R11)。
  複数あれば、必須・読み取り専用・未知の項目(本文の順)、値の違反(項目の定義順)の順に全部返す。
"""

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

from loreley_crawler.api.errors import (
    ConfigInvalidError,
    FieldError,
    InvalidRequestError,
    Reason,
)
from loreley_crawler.common.display_text import format_display_text
from loreley_crawler.sources import (
    ConnectorError,
    ConnectorRegistry,
    ErrorCategory,
    NewSource,
    SourceSettingsInput,
    check_source_id,
    validate_connector_config,
    validate_source_values,
)

JOB_ID_MAX_BYTES = 256
# `config_invalid` の説明文の長さの上限(architecture 11章の `failure_detail` と同じ)。Connector が
# 切り詰めと制御文字のエスケープ済みの説明文を返す前提の、念のための安全網。
CONFIG_INVALID_MESSAGE_MAX_CHARS = 512

# 未知の項目名を応答に載せるときの長さの上限(項目名はクライアントの入力。切り詰めと制御文字の
# エスケープを通す。孤立サロゲートは JSON にできず、応答が 500 になるので置き換える)。
FIELD_NAME_MAX_CHARS = 100

_LONE_SURROGATE = re.compile("[\ud800-\udfff]")
_BODY = "body"

_CRAWL_OPTION_FIELDS = ("force_delete", "rewrite_mode")
# `schedule_cron` は省略できる(null = 手動のみ)。
_REQUIRED_SETTING_FIELDS = ("connector_config", "ttl", "ratio_threshold", "min_delete_count")
_SETTING_FIELDS = (*_REQUIRED_SETTING_FIELDS, "schedule_cron")
_NEW_SOURCE_FIELDS = ("source_id", "connector_type", *_SETTING_FIELDS)
_REQUIRED_NEW_SOURCE_FIELDS = ("source_id", "connector_type", *_REQUIRED_SETTING_FIELDS)
_SERVER_SET_FIELDS = ("status", "updated_at")
# 更新では、パスと登録時に決まる項目も変更できない(`unknown_field` ではなく `read_only`)。
_READ_ONLY_ON_UPDATE = (*_SERVER_SET_FIELDS, "source_id", "connector_type")


@dataclass(frozen=True)
class CrawlOptions:
    force_delete: bool
    rewrite_mode: bool


# --- パスの検証 ---


def check_source_id_path(source_id: str) -> None:
    problem = check_source_id(source_id)
    if problem is not None:
        raise InvalidRequestError([FieldError("source_id", Reason(problem.reason.value))])


def check_job_id_path(job_id: str) -> None:
    """256 バイト以内・制御文字なし・空でない(CA-K-13 と同じ規則。crawler-api 3.2)。"""
    if not _is_valid_job_id(job_id):
        raise InvalidRequestError([FieldError("job_id", Reason.FORMAT)])


def _is_valid_job_id(job_id: str) -> bool:
    if not job_id or _LONE_SURROGATE.search(job_id):
        return False
    if len(job_id.encode("utf-8")) > JOB_ID_MAX_BYTES:
        return False
    return not any(unicodedata.category(character) == "Cc" for character in job_id)


# --- ボディの検証 ---


def parse_crawl_options(body: bytes) -> CrawlOptions:
    """クロール起動のボディ(任意。空は `{}` と同じ)。"""
    fields: dict[str, Any] = _parse_object(body) if body else {}
    errors = _structural_errors(fields, accepted=_CRAWL_OPTION_FIELDS)
    errors += [
        FieldError(name, Reason.TYPE)
        for name in _CRAWL_OPTION_FIELDS
        if name in fields and type(fields[name]) is not bool
    ]
    if errors:
        raise InvalidRequestError(errors)
    return CrawlOptions(
        force_delete=fields.get("force_delete", False),
        rewrite_mode=fields.get("rewrite_mode", False),
    )


def parse_new_source(body: bytes, registry: ConnectorRegistry) -> NewSource:
    fields = _parse_object(body)
    _raise_if_invalid(
        fields,
        accepted=_NEW_SOURCE_FIELDS,
        required=_REQUIRED_NEW_SOURCE_FIELDS,
        read_only=_SERVER_SET_FIELDS,
        registry=registry,
    )
    return NewSource(
        source_id=fields["source_id"],
        connector_type=fields["connector_type"],
        settings=_to_settings(fields),
    )


def parse_source_update(body: bytes, registry: ConnectorRegistry) -> SourceSettingsInput:
    """更新は、変更できる項目の全置換(部分更新はしない。crawler-api 4.4.3)。"""
    fields = _parse_object(body)
    _raise_if_invalid(
        fields,
        accepted=_SETTING_FIELDS,
        required=_REQUIRED_SETTING_FIELDS,
        read_only=_READ_ONLY_ON_UPDATE,
        registry=registry,
    )
    return _to_settings(fields)


def check_connector_config(
    registry: ConnectorRegistry, connector_type: str, connector_config: object
) -> None:
    """Connector の `validate_config`(I/O なし)。違反は 400 `config_invalid`、それ以外は 500。"""
    try:
        validate_connector_config(registry, connector_type, connector_config)
    except ConnectorError as error:
        if error.category is not ErrorCategory.CONFIG_INVALID:
            raise  # `connector_internal_error`: 想定外の異常として、中身を出さずに 500 にする
        message = format_display_text(error.message, max_chars=CONFIG_INVALID_MESSAGE_MAX_CHARS)
        raise ConfigInvalidError(message) from None


def _to_settings(fields: Mapping[str, Any]) -> SourceSettingsInput:
    """検証済みの項目から作る。`schedule_cron` の省略は null(手動のみ)。"""
    return SourceSettingsInput(
        connector_config=fields["connector_config"],
        ttl=fields["ttl"],
        ratio_threshold=fields["ratio_threshold"],
        min_delete_count=fields["min_delete_count"],
        schedule_cron=fields.get("schedule_cron"),
    )


def _raise_if_invalid(
    fields: Mapping[str, Any],
    *,
    accepted: tuple[str, ...],
    required: tuple[str, ...],
    read_only: tuple[str, ...],
    registry: ConnectorRegistry,
) -> None:
    errors = _structural_errors(fields, accepted=accepted, required=required, read_only=read_only)
    accepted_values = {name: fields[name] for name in accepted if name in fields}
    errors += [
        FieldError(problem.field, Reason(problem.reason.value))
        for problem in validate_source_values(accepted_values, registry)
    ]
    connector_config = fields.get("connector_config")
    if isinstance(connector_config, dict):
        # `sources` は JSON のオブジェクトかだけを見る。中の有限でない数値などは、ここで弾く。
        content_problem = _json_problem(connector_config)
        if content_problem is not None:
            errors.append(FieldError("connector_config", content_problem))
    if errors:
        raise InvalidRequestError(errors)


def _structural_errors(
    fields: Mapping[str, object],
    *,
    accepted: Iterable[str],
    required: Iterable[str] = (),
    read_only: Iterable[str] = (),
) -> list[FieldError]:
    read_only_names = frozenset(read_only)
    accepted_names = frozenset(accepted)
    errors = [FieldError(name, Reason.REQUIRED) for name in required if name not in fields]
    for name in fields:
        if name in read_only_names:
            errors.append(FieldError(name, Reason.READ_ONLY))
        elif name not in accepted_names:
            shown_name = format_display_text(name, max_chars=FIELD_NAME_MAX_CHARS)
            errors.append(FieldError(shown_name, Reason.UNKNOWN_FIELD))
    return errors


def _parse_object(body: bytes) -> dict[str, Any]:
    """UTF-8 の JSON のオブジェクトを読む。JSON でない・オブジェクトでないボディは 400。"""
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError):  # UnicodeDecodeError・JSONDecodeError は ValueError
        raise InvalidRequestError() from None
    if not isinstance(parsed, dict):
        raise InvalidRequestError([FieldError(_BODY, Reason.TYPE)])
    return parsed


def _json_problem(value: object) -> Reason | None:
    """入れ子の値に、有限でない数値(`type`)か孤立サロゲート(`format`)があるか。

    再帰せずに走査する(深い入れ子で `RecursionError` にならないように)。孤立サロゲートは
    UTF-8 にできず、保存で 500 になるので、400 にする。
    """
    found: Reason | None = None
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, float) and not isfinite(current):
            return Reason.TYPE
        if isinstance(current, str) and _LONE_SURROGATE.search(current):
            found = Reason.FORMAT
        elif isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return found
