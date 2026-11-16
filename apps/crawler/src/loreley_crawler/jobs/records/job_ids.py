"""ジョブ ID の生成(architecture 3.3・CA-P-1)。

形式は `job-{UTC 日時}-{16 進 8 桁の乱数}`(例 `job-20261113T010203Z-3fa9c2d1`)。`crawl_id` として
Indexer に送り、全ソースを通じて一意でなければならない。衝突は、ジョブ記録の `create` で検出する。
256 バイト以内・制御文字なし(CA-K-13)は、形式から常に満たす。
"""

import secrets
from collections.abc import Callable
from datetime import UTC

from loreley_crawler.common.clock import Clock

RandomToken = Callable[[], str]


def random_hex_token() -> str:
    return secrets.token_hex(4)


def generate_job_id(clock: Clock, random_token: RandomToken = random_hex_token) -> str:
    """`random_token` は、16 進 8 桁の文字列を返すこと(テストで差し替える)。"""
    timestamp = clock.now().astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"job-{timestamp}-{random_token()}"
