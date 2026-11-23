"""`SourceSettings` の元と `malformed` の判定(EP-02。C 5.7・5.8)。

保存値(`_source`)が読めない項目は `None` にし、`malformed` に項目名(応答の項目名)を載せる
(`unavailable.<項目名>=malformed`)。`ttl_days` は `ttl_seconds` から導出するので、`ttl_seconds` が
`malformed` なら `None`(キーは `ttl_seconds` だけ)。`source_id` は文書の `_id` で、`_source` の値は
見ない。
"""

from dataclasses import dataclass

from loreley_api.admin.base.codes import SourceStatus
from loreley_api.admin.derivation.units import ratio_to_percent, ttl_seconds_to_days
from loreley_api.admin.derivation.values import (
    Document,
    read_choice,
    read_instant_text,
    read_int,
    read_mapping,
    read_number,
    read_str,
)


@dataclass(frozen=True)
class SourceSettingsView:
    source_id: str
    connector_type: str | None
    connector_config: Document | None
    ttl_seconds: int | None
    ttl_days: int | None
    ratio_threshold_percent: int | float | None
    min_delete_count: int | None
    schedule_cron: str | None
    status: SourceStatus | None
    updated_at: str | None
    # 読めなかった項目の名前(`SourceSettings` の項目名)。
    malformed: tuple[str, ...]


def read_source_settings(record_id: str, source: Document) -> SourceSettingsView:
    connector_type = read_str(source.get("connector_type"))
    connector_config = read_mapping(source.get("connector_config"))
    ttl_seconds = read_int(source.get("ttl"))
    ratio = read_number(source.get("ratio_threshold"))
    ratio_threshold_percent = ratio_to_percent(ratio) if ratio is not None else None
    min_delete_count = read_int(source.get("min_delete_count"))
    # `null`(手動のみ)は正当な値。キーがない場合も `null` として読む。
    schedule_cron_value = source.get("schedule_cron")
    schedule_cron = read_str(schedule_cron_value)
    status = read_choice(source.get("status"), SourceStatus)
    updated_at = read_instant_text(source.get("updated_at"))

    checks = (
        ("connector_type", connector_type is not None),
        ("connector_config", connector_config is not None),
        ("ttl_seconds", ttl_seconds is not None),
        ("ratio_threshold_percent", ratio_threshold_percent is not None),
        ("min_delete_count", min_delete_count is not None),
        ("schedule_cron", schedule_cron_value is None or schedule_cron is not None),
        ("status", status is not None),
        ("updated_at", updated_at is not None),
    )
    return SourceSettingsView(
        source_id=record_id,
        connector_type=connector_type,
        connector_config=connector_config,
        ttl_seconds=ttl_seconds,
        ttl_days=ttl_seconds_to_days(ttl_seconds) if ttl_seconds is not None else None,
        ratio_threshold_percent=ratio_threshold_percent,
        min_delete_count=min_delete_count,
        schedule_cron=schedule_cron,
        status=status,
        updated_at=updated_at,
        malformed=tuple(name for name, is_readable in checks if not is_readable),
    )


@dataclass(frozen=True)
class SourceRowView:
    """EP-01 の行のうち、設定に由来する項目。読めない値は `None`(`unavailable` には載せない)。"""

    source_id: str
    connector_type: str | None
    schedule_cron: str | None
    status: SourceStatus | None


def read_source_row(record_id: str, source: Document) -> SourceRowView:
    """`connector_config` を読まない一覧用(R-1 は `connector_config` を除く)。"""
    return SourceRowView(
        source_id=record_id,
        connector_type=read_str(source.get("connector_type")),
        schedule_cron=read_str(source.get("schedule_cron")),
        status=read_choice(source.get("status"), SourceStatus),
    )
