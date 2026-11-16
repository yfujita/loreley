"""`indexer_client` への入力の型(Indexer の API の項目。indexer-api 3・4章)。"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True)
class LockInfo:
    """ロック所有情報。Indexer が、ロック文書(`loreley-jobs`)と照合する。"""

    owner: str
    job_id: str


class FinishOutcome(StrEnum):
    ENUMERATION_COMPLETED = "enumeration_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class DocumentToRegister:
    """バッチ登録の文書 1 件(indexer-api 4.3)。

    `raw_content` は原本のバイト列で、送るときに標準の base64(パディングあり・改行なし)にする。
    `external_id` は規則適用後の最終形、`content_hash`・`size` は `documents` が導出した値を渡す
    (ここでは検証も算出もしない)。`url`・`path` は任意で、`None` なら項目ごと送らない。
    `repr` に本文を出さない(R11)。
    """

    external_id: str
    title: str
    mime_type: str
    raw_content: bytes = field(repr=False)
    content_hash: str
    source_updated_at: datetime
    size: int
    url: str | None = None
    path: str | None = None
