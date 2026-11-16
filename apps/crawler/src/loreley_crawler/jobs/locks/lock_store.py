"""ロック文書の読み書き(module 4.4 の `locks/`。architecture 5.1〜5.5)。

`loreley-jobs` に書く層(`records/` と `locks/`)の一部。書き込みは `create` か、読んだ版を条件にした
置き換え・削除だけ。リトライは呼び出し側(受付・Job Runner)が行い、ここは 1 回の試行(競合は読み直して
判定し直す)で、`StoreUnavailableError` はそのまま送出する。

**応答が失われた後のリトライ**(0007 §4-3): 最初の書き込みが成功していたために `AlreadyExists`・
`Conflict` が返りうる。取得(`create`)は、読み直して `owner`・`job_id` が自分なら成功として扱う。
リースの設定は、読み直して自分のロックなら読んだ版でやり直す(同じ内容を書くので害がない)。
解放は、読み直してロックがなければ(自分の削除が成功していた場合を含む)完了として扱う。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from loreley_crawler.common.clock import Clock
from loreley_crawler.common.conflict import MAX_CONFLICT_ATTEMPTS
from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.common.timestamps import format_instant, parse_instant
from loreley_crawler.infrastructure.opensearch import (
    LIST_MAX_SIZE,
    Deleted,
    RecordFilter,
    Repository,
    SortKey,
    StoredRecord,
    Written,
)
from loreley_crawler.jobs.locks.lock_document import (
    LOCK_RECORD_TYPE,
    LockDocument,
    lock_record_id,
    new_lock_fields,
    parse_lock,
)


@dataclass(frozen=True)
class Acquired:
    lock: LockDocument


@dataclass(frozen=True)
class LockHeld:
    """すでにロックがある(受付は拒否する)。`holder` は読んだ既存のロック。"""

    holder: LockDocument


@dataclass(frozen=True)
class LeaseSet:
    """リースを設定・更新した。`lease_expires_at` は、書いた期限(ミリ秒に丸めた値)。"""

    lock: LockDocument
    lease_expires_at: datetime


@dataclass(frozen=True)
class LockNotOwned:
    """リースを設定できない: ロックがない・他のジョブのもの・(要求したときは)期限切れ。"""

    reason: str


@dataclass(frozen=True)
class LockDeleted:
    """読んだ版の削除に成功した。"""


@dataclass(frozen=True)
class LockChanged:
    """読んだ版の後に、ロック文書が書き換わった(または消えた)。読み直して判断する。"""


@dataclass(frozen=True)
class Released:
    """自分のロックを削除した、またはすでになかった。"""


@dataclass(frozen=True)
class NotReleased:
    """他のジョブのロックになっていたので、削除しなかった。"""

    reason: str


AcquireResult = Acquired | LockHeld
LeaseResult = LeaseSet | LockNotOwned
DeleteLockResult = LockDeleted | LockChanged
ReleaseResult = Released | NotReleased


class LockStore:
    def __init__(self, repository: Repository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    def read(self, source_id: str) -> LockDocument | None:
        stored = self._repository.fetch(lock_record_id(source_id))
        return parse_lock(stored) if stored is not None else None

    def list_locks(self) -> list[LockDocument]:
        """すべてのロック文書(起動時の回復が、孤児ロックなどを探す)。

        ロックは 1 ソースに 1 つなので件数は少ない。上限に達したら、取りこぼした一覧を成功に
        しない(回復の取りこぼしは、解放されないロックになる)。
        """
        records = self._repository.list_records(
            RecordFilter(equals={"record_type": LOCK_RECORD_TYPE}),
            [SortKey("source_id")],
            limit=LIST_MAX_SIZE,
        )
        if len(records) >= LIST_MAX_SIZE:
            raise StoreUnexpectedResponseError("lock_list_truncated")
        return [parse_lock(record) for record in records]

    def acquire(self, *, source_id: str, owner: str, job_id: str) -> AcquireResult:
        """ロック文書を `create` する(存在しない場合だけ成功。architecture 5.2)。"""
        record_id = lock_record_id(source_id)
        for _ in range(MAX_CONFLICT_ATTEMPTS):
            fields = new_lock_fields(
                source_id=source_id, owner=owner, job_id=job_id, acquired_at=self._clock.now()
            )
            outcome = self._repository.create(record_id, fields)
            if isinstance(outcome, Written):
                stored = StoredRecord(record_id, fields, outcome.seq_no, outcome.primary_term)
                return Acquired(parse_lock(stored))
            holder = self.read(source_id)
            if holder is None:
                continue  # 読む前に消えた(解放の直後)。取り直す
            if holder.is_held_by(owner, job_id):
                return Acquired(holder)  # 応答が失われた最初の `create` が成功していた
            return LockHeld(holder)
        raise StoreUnavailableError("lock_acquire_contention")

    def set_lease(
        self, lock: LockDocument, *, lease_seconds: float, require_active_lease: bool
    ) -> LeaseResult:
        """`lease_expires_at` を現在時刻 + `lease_seconds` に、`heartbeat_at` を現在時刻にする。

        読んだ版(`lock`)を条件にする。版が合わなければ読み直し、ロックがない・他のジョブの
        ものなら `LockNotOwned`(所有権の喪失)。自分のロックなら、読んだ版でやり直す。
        - 実行開始のリース設定(`require_active_lease=False`): 受付直後は期限が null、回復後は
          過去の期限が残っていてもよい(architecture 5.1・5.8)。
        - ハートビート(`require_active_lease=True`): 読み直したロックの期限が切れていれば、
          Indexer から見て所有していないので、`LockNotOwned("lease_expired")`(5.3)。
        """
        current = lock
        for _ in range(MAX_CONFLICT_ATTEMPTS):
            now = self._clock.now()
            # 保存される値(ミリ秒に切り捨て)と同じ値を、期限として返す。
            lease_text = format_instant(now + timedelta(seconds=lease_seconds))
            body = {
                **current.raw,
                "lease_expires_at": lease_text,
                "heartbeat_at": format_instant(now),
            }
            outcome = self._repository.replace_if_unchanged(
                lock_record_id(lock.source_id),
                body,
                seq_no=current.seq_no,
                primary_term=current.primary_term,
            )
            if isinstance(outcome, Written):
                stored = StoredRecord(
                    lock_record_id(lock.source_id), body, outcome.seq_no, outcome.primary_term
                )
                return LeaseSet(parse_lock(stored), parse_instant(lease_text))
            # 記録がない場合も `Conflict`(実 OpenSearch 3.9.0)。読み直して判定する。
            reread = self.read(lock.source_id)
            if reread is None:
                return LockNotOwned("lock_missing")
            if not reread.is_held_by(lock.owner, lock.job_id):
                return LockNotOwned("lock_taken_over")
            if require_active_lease and not reread.has_active_lease(self._clock.now()):
                return LockNotOwned("lease_expired")
            current = reread
        raise StoreUnavailableError("lease_contention")

    def delete_unchanged(self, lock: LockDocument) -> DeleteLockResult:
        """読んだ版を条件に削除する(1 回の試行)。誰のロックかは見ない。

        受付の巻き戻し・`queued` の取り消し・管理者の解放・回復は、それぞれ対象を判断した後、
        これで消し、`LockChanged` なら読み直して判断し直す。
        """
        outcome = self._repository.delete_if_unchanged(
            lock_record_id(lock.source_id), seq_no=lock.seq_no, primary_term=lock.primary_term
        )
        return LockDeleted() if isinstance(outcome, Deleted) else LockChanged()

    def release_own(self, lock: LockDocument) -> ReleaseResult:
        """自分のロックを削除する(通常の解放。architecture 5.5)。

        条件が外れたときは読み直し、自分のものなら再試行し、他のジョブのものなら何もしない。
        ロックがなければ完了(最初の削除が成功していた場合を含む)。ハートビートを止めてから呼ぶこと。
        所有権の喪失を記録しているときに呼ぶかは、呼び出し側(Job Runner)が決める(5.7)。
        """
        current = lock
        for _ in range(MAX_CONFLICT_ATTEMPTS):
            if isinstance(self.delete_unchanged(current), LockDeleted):
                return Released()
            reread = self.read(lock.source_id)
            if reread is None:
                return Released()
            if not reread.is_held_by(lock.owner, lock.job_id):
                return NotReleased("lock_taken_over")
            current = reread
        raise StoreUnavailableError("lock_release_contention")
