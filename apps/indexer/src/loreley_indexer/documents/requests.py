"""登録・`last-seen` の入力(api 3.2、4.2、4.3)。

HTTP の形式検証と base64 のデコードは api 層が行い、ここには検証済みの値が届く。
`fetched_at`・`metadata` や未知の項目は api 層が捨てる(保存せず、エラーにもしない。plan 案7)。
"""

from dataclasses import dataclass
from datetime import datetime

from loreley_indexer.common.locks import LockInfo


@dataclass(frozen=True)
class CrawlContext:
    """バッチ登録と `last-seen` に共通の、クロールの実行コンテキスト。"""

    source_id: str
    crawl_id: str
    crawl_started_at: datetime
    lock: LockInfo


@dataclass(frozen=True)
class DocumentInput:
    """`documents[]` の要素。`raw_content` は base64 をデコードした原本。"""

    external_id: str
    title: str
    mime_type: str
    raw_content: bytes
    content_hash: str  # Crawler の値を信用する。照合も再計算もしない(plan 案4)
    source_updated_at: datetime
    size: int  # 申告された原本のバイト数
    url: str | None = None
    path: str | None = None
