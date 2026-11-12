"""`loreley-jobs`(Crawler の領域)の読み取り専用の窓口(R6)。

ロック文書とメンテナンスフラグの形式は設計書に未定義の仮定義(plan 0002 §3.1):
- ロック文書: ID `lock-{source_id}`、項目 `owner`、`job_id`、`lease_expires_at`(ISO 8601)
- メンテナンスフラグ: ID `maintenance`、項目 `enabled`(bool)。文書なしは「立っていない」。
  文書があり `enabled` が真偽値の `False` と明示されているときだけ「立っていない」で、
  それ以外(欠落・`"true"`・`1`・非 bool)は「立っている」とみなす(fail-closed。0014)
Crawler の設計で決まったら、このファイルと `common/locks.py` だけを直す。
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from loreley_indexer.common.locks import LockRecord
from loreley_indexer.common.timestamps import parse_instant
from loreley_indexer.infrastructure.opensearch.store import StoreReader

LOCK_RECORD_ID_PREFIX = "lock-"
MAINTENANCE_RECORD_ID = "maintenance"

logger = logging.getLogger(__name__)


class JobsReader(ABC):
    @abstractmethod
    def fetch_lock(self, source_id: str) -> LockRecord | None:
        pass

    @abstractmethod
    def is_maintenance_enabled(self) -> bool:
        pass


class StoreJobsReader(JobsReader):
    """書き込み用メソッドを持たない `StoreReader` だけを受け取り、読み取り専用を型で保つ。"""

    def __init__(self, jobs_store: StoreReader) -> None:
        self._jobs_store = jobs_store
        # 判定・バッチ・要約のたびに読むので、不正な値の WARNING はプロセスごとに、記録・項目名
        # ごとに 1 回にする(以降は DEBUG。判定は毎回「立っている」)。
        self._warned_malformed_fields: set[tuple[str, str]] = set()

    def fetch_lock(self, source_id: str) -> LockRecord | None:
        record = self._jobs_store.fetch(f"{LOCK_RECORD_ID_PREFIX}{source_id}")
        if record is None:
            return None
        return _parse_lock(record.source)

    def is_maintenance_enabled(self) -> bool:
        record = self._jobs_store.fetch(MAINTENANCE_RECORD_ID)
        if record is None:
            return False
        enabled = record.source.get("enabled")
        if enabled is False:
            return False
        if enabled is not True:
            # 削除・要約の書き戻しを止める側に倒す。値は出さず、記録の ID と項目名だけを残す。
            field = (MAINTENANCE_RECORD_ID, "enabled")
            is_first_time = field not in self._warned_malformed_fields
            self._warned_malformed_fields.add(field)
            logger.log(
                logging.WARNING if is_first_time else logging.DEBUG,
                "the maintenance flag is malformed, treated as enabled: record_id=%s field=%s",
                *field,
            )
        return True


def _parse_lock(source: dict[str, Any]) -> LockRecord | None:
    """形式が不正なロック文書は、所有を認めない側(None)に倒す。"""
    owner = source.get("owner")
    job_id = source.get("job_id")
    lease_expires_at = source.get("lease_expires_at")
    if not (
        isinstance(owner, str) and isinstance(job_id, str) and isinstance(lease_expires_at, str)
    ):
        return None
    try:
        return LockRecord(
            owner=owner, job_id=job_id, lease_expires_at=parse_instant(lease_expires_at)
        )
    except ValueError:
        return None
