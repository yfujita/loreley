"""Crawler に送るリクエスト本文の組み立て(B 9.2。D 4.9)。

本文を読まない API(取消・ロック解放・削除ジョブ起動)には本文を付けないので、ここには関数がない。
値の検証・変換(`ttl`・`ratio_threshold` の換算など)は済んでいる前提で、形を整えるだけ。
"""

import json
from typing import Any

from loreley_api.infrastructure.crawler_client.client import CrawlerSourceSettings


def register_payload(
    source_id: str, connector_type: str, settings: CrawlerSourceSettings
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "connector_type": connector_type,
        **_settings_fields(settings),
    }


def update_payload(settings: CrawlerSourceSettings) -> dict[str, Any]:
    """全置換(必須項目を省略しない。`schedule_cron` の省略は `null` に置き換わる。B 3.4)。"""
    return _settings_fields(settings)


def crawl_payload(*, force_delete: bool, rewrite_mode: bool) -> dict[str, Any]:
    """既定の `false` も省略せず、2 項目を常に明示する(B 4.1)。"""
    return {"force_delete": force_delete, "rewrite_mode": rewrite_mode}


def encode_json(payload: dict[str, Any]) -> bytes:
    """UTF-8 の JSON。`NaN`・`Infinity` は出さない(`ValueError`。Admin API の検証漏れの不具合)。

    `ensure_ascii` の既定(`True`)のまま使う: 孤立サロゲートも `\\ud800` の形で出せるので、
    送信の段階で `UnicodeEncodeError` にならず、Crawler の検証(400)に任せられる。
    """
    return json.dumps(payload, allow_nan=False).encode("ascii")


def _settings_fields(settings: CrawlerSourceSettings) -> dict[str, Any]:
    return {
        "connector_config": settings.connector_config,
        "ttl": settings.ttl_seconds,
        "ratio_threshold": settings.ratio_threshold,
        "min_delete_count": settings.min_delete_count,
        "schedule_cron": settings.schedule_cron,
    }
