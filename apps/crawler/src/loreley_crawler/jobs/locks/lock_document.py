"""ロック文書の形式(architecture 5.1・3.3.2)。

ID は `lock-{source_id}`。Indexer が読む項目は `owner`・`job_id`・`lease_expires_at` の 3 つで、
所有の判定は「`owner` と `job_id` が要請の `lock` と一致し、現在時刻が `lease_expires_at` より前」。
文書がない・期限切れ・不一致・**形式不正**は、すべて「所有していない」(Indexer の規則)。Crawler も
同じ側に倒して読む: 読めない日時は、リースは期限切れ(`EXPIRED`)、`acquired_at` は十分に古い
(`ANCIENT`)として扱う(管理者のロック解放・回復で、壊れたロックも解放できるようにするため)。

`owner` が文字列でない(壊れた)ロックは、`owner` を空文字として読む。自分の `owner` と一致しない
ので、**起動時の回復は他の Crawler のロックとして触らず**(警告だけ)、管理者のロック解放で消す。
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from loreley_crawler.common.timestamps import format_instant, parse_instant
from loreley_crawler.infrastructure.opensearch import StoredRecord

LOCK_RECORD_TYPE = "lock"
LOCK_ID_PREFIX = "lock-"

# 読めない `lease_expires_at`(期限切れ)と `acquired_at`(十分に古い)の代わりの値。
EXPIRED = datetime.min.replace(tzinfo=UTC)
ANCIENT = EXPIRED


def lock_record_id(source_id: str) -> str:
    return f"{LOCK_ID_PREFIX}{source_id}"


@dataclass(frozen=True)
class LockDocument:
    """読んだ(または書いた)ロック文書と、版条件つきの書き込みに使う版。"""

    source_id: str
    owner: str
    job_id: str
    lease_expires_at: datetime | None  # None は未設定(`queued` のジョブのロック)
    acquired_at: datetime
    seq_no: int
    primary_term: int
    raw: Mapping[str, Any] = field(repr=False, compare=False)

    def is_held_by(self, owner: str, job_id: str) -> bool:
        return self.owner == owner and self.job_id == job_id

    def has_active_lease(self, now: datetime) -> bool:
        """Indexer の判定と同じ。期限が未設定・期限以降なら、所有していない。"""
        return self.lease_expires_at is not None and now < self.lease_expires_at


def new_lock_fields(
    *, source_id: str, owner: str, job_id: str, acquired_at: datetime
) -> dict[str, Any]:
    """受付が `create` するロック文書。リースは未設定(null。実行開始で設定する)。"""
    return {
        "record_type": LOCK_RECORD_TYPE,
        "source_id": source_id,
        "owner": owner,
        "job_id": job_id,
        "lease_expires_at": None,
        "heartbeat_at": None,
        "acquired_at": format_instant(acquired_at),
    }


def parse_lock(stored: StoredRecord) -> LockDocument:
    source = stored.source
    owner = source.get("owner")
    job_id = source.get("job_id")
    return LockDocument(
        # 書き込み先の ID に使うので、本文ではなく ID から得る(本文が壊れていても取り違えない)。
        source_id=stored.id.removeprefix(LOCK_ID_PREFIX),
        owner=owner if isinstance(owner, str) else "",
        job_id=job_id if isinstance(job_id, str) else "",
        lease_expires_at=_parse_lease(source.get("lease_expires_at")),
        acquired_at=_parse_or(source.get("acquired_at"), ANCIENT),
        seq_no=stored.seq_no,
        primary_term=stored.primary_term,
        raw=dict(source),
    )


def _parse_lease(value: object) -> datetime | None:
    if value is None:
        return None
    return _parse_or(value, EXPIRED)


def _parse_or(value: object, fallback: datetime) -> datetime:
    if not isinstance(value, str):
        return fallback
    try:
        return parse_instant(value)
    except ValueError:
        return fallback
