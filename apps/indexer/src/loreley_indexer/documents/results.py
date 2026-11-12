"""登録と `last-seen` の文書単位の結果(api 4.2、4.3。名前は api の表のとおり)。"""

from dataclasses import dataclass
from enum import StrEnum


class Change(StrEnum):
    """本文・メタデータに関する変更区分(K50)。`last_seen_at` だけの更新は `UNCHANGED`。"""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


class FailureType(StrEnum):
    DOCUMENT_REJECTED = "document_rejected"  # 文書固有の拒否。Crawler がリトライ後にスキップ
    LOCK_NOT_OWNED = "lock_not_owned"
    WRITE_CONFLICT = "write_conflict"  # 読み直しの上限を超えた。再試行可能(K51)
    UPDATE_CONFLICT = "update_conflict"  # `last_seen_at` の Update が `retry_on_conflict` 超過
    OVERSIZE = "oversize"  # 原本サイズ超過(仮名。plan 案1)。リトライしない


@dataclass(frozen=True)
class DocumentRegistered:
    """`status=ok`。"""

    external_id: str
    document_id: str
    change: Change
    extract_failed: bool


@dataclass(frozen=True)
class DocumentFailed:
    """`status=failed`。`message` は固定文(文書の内容を含めない)。"""

    external_id: str
    document_id: str
    failure_type: FailureType
    message: str


DocumentOutcome = DocumentRegistered | DocumentFailed


class LastSeenResult(StrEnum):
    UPDATED = "updated"
    UNCHANGED = "unchanged"  # 現在値以上のため書かなかった。`Change.UNCHANGED` とは別の概念
    NOT_FOUND = "not_found"
    UPDATE_CONFLICT = "update_conflict"
    LOCK_NOT_OWNED = "lock_not_owned"


@dataclass(frozen=True)
class LastSeenEntry:
    document_id: str
    result: LastSeenResult
