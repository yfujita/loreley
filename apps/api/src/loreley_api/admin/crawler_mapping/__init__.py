"""Crawler の応答・失敗を Admin API の成功・エラーに写す(B 2.6・9.2。D 4.7)。"""

from loreley_api.admin.crawler_mapping.table import CrawlerOperation
from loreley_api.admin.crawler_mapping.translate import (
    RequestedOptions,
    TtlField,
    needs_lock_state,
    translate,
)

__all__ = [
    "CrawlerOperation",
    "RequestedOptions",
    "TtlField",
    "needs_lock_state",
    "translate",
]
