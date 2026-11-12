"""Store 層(`loreley-deletions`、`loreley-jobs`)のインメモリ fake。1 インスタンスが 1 索引。

ID 取得と一覧はどちらも最新の状態を返す(実アダプタは一覧の前に refresh するため)。
"""

import copy
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    Deleted,
    DeleteOutcome,
    NotFound,
    RecordFilter,
    SortKey,
    StoredDocument,
    StoreRepository,
    WriteOutcome,
    Written,
)
from loreley_indexer.infrastructure.opensearch.store import LIST_MAX_SIZE
from tests.fakes.behavior import FakeBehavior

PRIMARY_TERM = 1

FETCH = "fetch"
LIST = "list_records"
SAVE = "save"
REPLACE = "replace_if_unchanged"
DELETE = "delete"
WRITE_OPERATIONS = (SAVE, REPLACE, DELETE)


@dataclass
class _Entry:
    source: dict[str, Any]
    seq_no: int


class InMemoryStore(StoreRepository):
    def __init__(self) -> None:
        self.behavior = FakeBehavior()
        # 各操作の本体(フック・差し替えの後)を直列にする。検索インデックスの fake と同じ理由。
        self._lock = threading.RLock()
        self._records: dict[str, _Entry] = {}
        self._next_seq_no = 0

    def fetch(self, record_id: str) -> StoredDocument | None:
        if (intercepted := self.behavior.enter(FETCH, record_id)) is not None:
            return intercepted.value
        with self._lock:
            entry = self._records.get(record_id)
            return self._to_stored(record_id, entry) if entry is not None else None

    def list_records(
        self, record_filter: RecordFilter, sort: Sequence[SortKey], *, limit: int
    ) -> list[StoredDocument]:
        if not 1 <= limit <= LIST_MAX_SIZE:
            raise ValueError(f"limit must be between 1 and {LIST_MAX_SIZE}")
        if (intercepted := self.behavior.enter(LIST)) is not None:
            return intercepted.value
        with self._lock:
            matching = [
                self._to_stored(record_id, entry)
                for record_id, entry in self._records.items()
                if _matches(record_filter, entry.source)
            ]
        # 後ろのキーから順に安定ソートすると、複数キーの優先順位が先頭のキーになる。
        for key in reversed(sort):
            matching.sort(key=_sort_function(key), reverse=key.descending)
        return matching[:limit]

    def save(self, record_id: str, body: Mapping[str, Any]) -> WriteOutcome:
        if (intercepted := self.behavior.enter(SAVE, record_id)) is not None:
            return intercepted.value
        with self._lock:
            return self._write(record_id, body)

    def replace_if_unchanged(
        self, record_id: str, body: Mapping[str, Any], *, seq_no: int, primary_term: int
    ) -> WriteOutcome:
        if (intercepted := self.behavior.enter(REPLACE, record_id)) is not None:
            return intercepted.value
        with self._lock:
            entry = self._records.get(record_id)
            if entry is None:
                return NotFound()
            if entry.seq_no != seq_no or primary_term != PRIMARY_TERM:
                return Conflict()
            return self._write(record_id, body)

    def delete(self, record_id: str) -> DeleteOutcome:
        if (intercepted := self.behavior.enter(DELETE, record_id)) is not None:
            return intercepted.value
        with self._lock:
            if record_id not in self._records:
                return NotFound()
            del self._records[record_id]
            self._next_seq_no += 1
            return Deleted()

    # --- テストの準備・確認用(フックを通らず、呼び出しとして記録されない) ---

    def seed(self, record_id: str, body: Mapping[str, Any]) -> StoredDocument:
        """記録を直接置く。別の書き手による書き込みの再現にも使う(seq_no が進む)。"""
        with self._lock:
            self._write(record_id, body)
            return self._to_stored(record_id, self._records[record_id])

    def body_of(self, record_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._records.get(record_id)
            return copy.deepcopy(entry.source) if entry is not None else None

    def record_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._records)

    def write_calls(self) -> list[str]:
        return [call.operation for call in self.behavior.calls_of(*WRITE_OPERATIONS)]

    # --- 内部(呼び出し側が `_lock` を持っていること) ---

    def _write(self, record_id: str, body: Mapping[str, Any]) -> Written:
        created = record_id not in self._records
        entry = _Entry(source=copy.deepcopy(dict(body)), seq_no=self._next_seq_no)
        self._next_seq_no += 1
        self._records[record_id] = entry
        return Written(seq_no=entry.seq_no, primary_term=PRIMARY_TERM, created=created)

    @staticmethod
    def _to_stored(record_id: str, entry: _Entry) -> StoredDocument:
        return StoredDocument(
            id=record_id,
            source=copy.deepcopy(entry.source),
            seq_no=entry.seq_no,
            primary_term=PRIMARY_TERM,
        )


def _matches(record_filter: RecordFilter, source: Mapping[str, Any]) -> bool:
    if any(source.get(name) != value for name, value in record_filter.equals.items()):
        return False
    if any(source.get(name) not in values for name, values in record_filter.one_of.items()):
        return False
    if any(source.get(name) is None for name in record_filter.exists):
        return False
    return all(source.get(name) is None for name in record_filter.missing)


def _sort_function(key: SortKey) -> Callable[[StoredDocument], tuple[bool, Any]]:
    """値のない記録は、昇順でも降順でも末尾に置く(OpenSearch の `missing: _last` と同じ)。"""

    def sort_value(record: StoredDocument) -> tuple[bool, Any]:
        value = record.source.get(key.field_name)
        is_missing = value is None
        # 降順は `reverse=True` で並べるため、値なしが先頭に来ないよう先頭の要素を反転する。
        return (is_missing != key.descending, 0 if is_missing else value)

    return sort_value
