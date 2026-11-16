"""`loreley-sources` の記録の形式と、読み戻し(architecture 3.2。module 4.3)。

記録の項目名は architecture 3.2 のとおり。ID は `source_id`。`connector_config` は不透明な値で、
ログ・例外・`repr` に出さない(認証情報の参照名を含みうる。R11)。そのため、形式が不正な記録は
`MalformedSourceRecord` に項目名だけを載せて返し、値は載せない。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from math import isfinite
from typing import Any

from loreley_crawler.common.timestamps import format_instant, parse_instant
from loreley_crawler.infrastructure.opensearch import StoredRecord
from loreley_crawler.sources.schedule_cron import is_valid_schedule_cron


class SourceStatus(StrEnum):
    ACTIVE = "active"
    DELETING = "deleting"


@dataclass(frozen=True)
class SourceSettingsInput:
    """登録・更新で渡す、変更できる項目。値の規則は `validation.py` で検証済みとする。"""

    connector_config: dict[str, Any] = field(repr=False)
    ttl: int
    ratio_threshold: float
    min_delete_count: int
    schedule_cron: str | None


@dataclass(frozen=True)
class NewSource:
    source_id: str
    connector_type: str
    settings: SourceSettingsInput


@dataclass(frozen=True)
class SourceRecord:
    """読んだ時点の設定レコード全体(1 回の読み取りの結果を 1 つの値にしたもの。CA-P-51)。"""

    source_id: str
    connector_type: str
    connector_config: dict[str, Any] = field(repr=False)
    ttl: int
    ratio_threshold: float
    min_delete_count: int
    schedule_cron: str | None
    status: SourceStatus
    updated_at: datetime


@dataclass(frozen=True)
class MalformedSourceRecord:
    """値が欠けている・型が合わない設定レコード。`crawl` は `config_invalid` で `failed` にする。

    `status`・`connector_type` は、読めたときだけ入る(`deleting` の判定と、`api` が更新の
    `connector_config` を検証する型の取得に使う)。`connector_type` は Connector の種別名で、
    設定の値ではない。他の値は含めない。
    """

    source_id: str
    invalid_fields: tuple[str, ...]
    status: SourceStatus | None
    connector_type: str | None = None


StoredSource = SourceRecord | MalformedSourceRecord


def build_body(
    source_id: str,
    connector_type: str,
    settings: SourceSettingsInput,
    *,
    status: SourceStatus,
    updated_at: datetime,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "connector_type": connector_type,
        "connector_config": settings.connector_config,
        "ttl": settings.ttl,
        "ratio_threshold": settings.ratio_threshold,
        "min_delete_count": settings.min_delete_count,
        "schedule_cron": settings.schedule_cron,
        "status": status.value,
        "updated_at": format_instant(updated_at),
    }


def parse_stored_source(stored: StoredRecord) -> StoredSource:
    source = stored.source
    status = _parse_status(source.get("status"))
    updated_at = _parse_updated_at(source.get("updated_at"))
    invalid_fields = tuple(
        name
        for name, is_valid in (
            ("source_id", source.get("source_id") == stored.id),
            ("connector_type", isinstance(source.get("connector_type"), str)),
            ("connector_config", isinstance(source.get("connector_config"), dict)),
            ("ttl", type(source.get("ttl")) is int),
            ("ratio_threshold", _is_finite_number(source.get("ratio_threshold"))),
            ("min_delete_count", type(source.get("min_delete_count")) is int),
            ("schedule_cron", _is_valid_schedule(source.get("schedule_cron"))),
            ("status", status is not None),
            ("updated_at", updated_at is not None),
        )
        if not is_valid
    )
    if invalid_fields or status is None or updated_at is None:
        connector_type = source.get("connector_type")
        return MalformedSourceRecord(
            stored.id,
            invalid_fields,
            status,
            connector_type if isinstance(connector_type, str) else None,
        )
    return SourceRecord(
        source_id=stored.id,
        connector_type=source["connector_type"],
        connector_config=source["connector_config"],
        ttl=source["ttl"],
        ratio_threshold=source["ratio_threshold"],
        min_delete_count=source["min_delete_count"],
        schedule_cron=source.get("schedule_cron"),
        status=status,
        updated_at=updated_at,
    )


def _parse_status(value: object) -> SourceStatus | None:
    try:
        return SourceStatus(value)
    except ValueError:
        return None


def _parse_updated_at(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return parse_instant(value)
    except ValueError:
        return None


def _is_finite_number(value: object) -> bool:
    return type(value) is int or (type(value) is float and isfinite(value))


def _is_valid_schedule(value: object) -> bool:
    # 項目がない(None)は手動のみ。値があれば 5 項目の cron 式。
    return value is None or (isinstance(value, str) and is_valid_schedule_cron(value))
