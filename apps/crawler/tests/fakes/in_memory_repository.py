"""`Repository` のメモリ上の実装(fake)。1 インスタンスが 1 索引。

`OpenSearchRepository` と同じ契約・同じ結果区分を実装する。実機の OpenSearch と食い違う可能性が
あるので、次は実 OpenSearch の統合テストで確認する(architecture 12章 #37。CM-U-1、CA-U-18)。
- 10,000 件の上限(`max_result_window`)・PIT の保持時間・refresh の遅れは再現しない
  (書き込みは取得にも一覧にも走査にも、すぐ反映される)。
- `create` と版条件つきの書き込みの原子性は、1 つのロックで直列にして再現する。
- 版条件つきの書き込み・削除で、記録がないときは `Conflict` を返す(実 OpenSearch 3.9.0 で
  確認した挙動。記録がない場合も 409)。`NotFound` は、テストが `behavior.inject` で注入する。
- クエリの忠実度: 項目は値の完全一致(スカラー)で比べる。配列の項目、空配列の `exists`、
  真偽値と整数の区別は再現しない(Crawler の記録はスカラーの項目だけ)。

実機でしか確認できない限界(P9・統合テストで確認する):
- `scan` の並べ替えが一意でない(`document_id` を持たない同種の記録が同じソースに 2 件以上)場合の
  `non_unique_sort`(実 OpenSearch の `search_after` の挙動)を再現しない。
- 降順ソートのキー(`queued_at` など)の、実マッピング(date・keyword)での順序は検証できない。

再現するもの: 版(`seq_no`)の条件、`create` の競合、PIT 相当の走査(開始時点のスナップショット)、
ID のバルク削除(存在しない ID は成功。部分失敗を注入できる)、割り込みフックと応答・例外の差し替え
(`behavior`。操作名はこのモジュールの定数)。開いたままの走査の数は `open_scan_count` で確認できる。
"""

import copy
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from itertools import batched
from typing import Any

from loreley_crawler.infrastructure.opensearch import (
    LIST_MAX_SIZE,
    AlreadyExists,
    BulkDeleteResult,
    Conflict,
    CreateOutcome,
    Deleted,
    DeleteOutcome,
    RecordFilter,
    RecordPages,
    ReplaceOutcome,
    Repository,
    RepositorySettings,
    SortKey,
    StoredRecord,
    Written,
)
from tests.fakes.behavior import FakeBehavior

PRIMARY_TERM = 1

FETCH = "fetch"
CREATE = "create"
REPLACE = "replace_if_unchanged"
DELETE = "delete_if_unchanged"
LIST = "list_records"
SCAN = "scan"  # 走査の開始(PIT を開く)。例外を差し込むと、開始に失敗する
SCAN_PAGE = "scan_page"  # ページの読み込み。例外を差し込むと、走査の途中で失敗する
DELETE_IDS = "delete_ids"
WRITE_OPERATIONS = (CREATE, REPLACE, DELETE, DELETE_IDS)


@dataclass
class _Entry:
    source: dict[str, Any]
    seq_no: int


class InMemoryRepository(Repository):
    def __init__(self, settings: RepositorySettings | None = None) -> None:
        self.behavior = FakeBehavior()
        self._settings = settings or RepositorySettings()
        # 各操作の本体(フック・差し替えの後)を直列にする。
        self._lock = threading.RLock()
        self._records: dict[str, _Entry] = {}
        self._next_seq_no = 0
        self._open_scan_count = 0
        self._failing_bulk_ids: dict[str, int | None] = {}

    # --- Repository ---

    def fetch(self, record_id: str) -> StoredRecord | None:
        if (intercepted := self.behavior.enter(FETCH, record_id)) is not None:
            return intercepted.value
        with self._lock:
            entry = self._records.get(record_id)
            return self._to_stored(record_id, entry) if entry is not None else None

    def create(self, record_id: str, body: Mapping[str, Any]) -> CreateOutcome:
        if (intercepted := self.behavior.enter(CREATE, record_id)) is not None:
            return intercepted.value
        with self._lock:
            if record_id in self._records:
                return AlreadyExists()
            return self._write(record_id, body)

    def replace_if_unchanged(
        self, record_id: str, body: Mapping[str, Any], *, seq_no: int, primary_term: int
    ) -> ReplaceOutcome:
        if (intercepted := self.behavior.enter(REPLACE, record_id)) is not None:
            return intercepted.value
        with self._lock:
            entry = self._records.get(record_id)
            if entry is None or entry.seq_no != seq_no or primary_term != PRIMARY_TERM:
                return Conflict()
            return self._write(record_id, body)

    def delete_if_unchanged(
        self, record_id: str, *, seq_no: int, primary_term: int
    ) -> DeleteOutcome:
        if (intercepted := self.behavior.enter(DELETE, record_id)) is not None:
            return intercepted.value
        with self._lock:
            entry = self._records.get(record_id)
            if entry is None or entry.seq_no != seq_no or primary_term != PRIMARY_TERM:
                return Conflict()
            del self._records[record_id]
            self._next_seq_no += 1
            return Deleted()

    def list_records(
        self, record_filter: RecordFilter, sort: Sequence[SortKey], *, limit: int
    ) -> list[StoredRecord]:
        if not 1 <= limit <= LIST_MAX_SIZE:
            raise ValueError(f"limit must be between 1 and {LIST_MAX_SIZE}")
        if (intercepted := self.behavior.enter(LIST)) is not None:
            return intercepted.value
        with self._lock:
            return self._matching_sorted(record_filter, sort)[:limit]

    def scan(
        self, record_filter: RecordFilter, *, sort: Sequence[SortKey]
    ) -> AbstractContextManager[RecordPages]:
        if not sort:
            raise ValueError("sort must include a unique tiebreaker")
        return self._scan(record_filter, sort)

    @contextmanager
    def _scan(self, record_filter: RecordFilter, sort: Sequence[SortKey]) -> Iterator[RecordPages]:
        self.behavior.enter(SCAN)  # 差し込んだ例外を送出する(応答の差し替えは使わない)
        # 開始時点のスナップショット(PIT 相当)。以後の書き込み・削除の影響を受けない。
        with self._lock:
            snapshot = self._matching_sorted(record_filter, sort)
            self._open_scan_count += 1
        try:
            yield self._pages(snapshot)
        finally:
            with self._lock:
                self._open_scan_count -= 1

    def delete_ids(self, record_ids: Sequence[str]) -> BulkDeleteResult:
        if (intercepted := self.behavior.enter(DELETE_IDS)) is not None:
            return intercepted.value
        unique_ids = tuple(dict.fromkeys(record_ids))
        failed_ids: list[str] = []
        for batch in batched(unique_ids, self._settings.bulk_delete_batch_size):
            with self._lock:
                for record_id in batch:
                    if self._consume_bulk_failure(record_id):
                        failed_ids.append(record_id)
                    elif record_id in self._records:
                        del self._records[record_id]
                        self._next_seq_no += 1
        return BulkDeleteResult(failed_ids=tuple(failed_ids))

    # --- テストの準備・確認用(フックを通らず、呼び出しとして記録されない) ---

    def fail_bulk_delete_of(self, record_ids: Sequence[str], *, times: int | None = 1) -> None:
        """次の `times` 回(None なら以後ずっと)、これらの ID のバルク削除を失敗させる(部分失敗)。

        失敗した ID は消さず、`BulkDeleteResult.failed_ids` に入る(同じ呼び出しの他の ID は消える)。
        """
        with self._lock:
            for record_id in record_ids:
                self._failing_bulk_ids[record_id] = times

    def seed(self, record_id: str, body: Mapping[str, Any]) -> StoredRecord:
        """記録を直接置く。別の書き手による書き込みの再現にも使う(版が進む)。"""
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

    @property
    def open_scan_count(self) -> int:
        with self._lock:
            return self._open_scan_count

    def write_calls(self) -> list[str]:
        return [call.operation for call in self.behavior.calls_of(*WRITE_OPERATIONS)]

    # --- 内部 ---

    def _pages(self, snapshot: list[StoredRecord]) -> RecordPages:
        page_size = self._settings.scan_page_size
        for start in range(0, len(snapshot), page_size):
            self.behavior.enter(SCAN_PAGE)  # 差し込んだ例外を送出する
            yield snapshot[start : start + page_size]

    def _matching_sorted(
        self, record_filter: RecordFilter, sort: Sequence[SortKey]
    ) -> list[StoredRecord]:
        matching = [
            self._to_stored(record_id, entry)
            for record_id, entry in self._records.items()
            if _matches(record_filter, entry.source)
        ]
        # 後ろのキーから順に安定ソートすると、複数キーの優先順位が先頭のキーになる。
        for key in reversed(sort):
            matching.sort(key=_sort_function(key), reverse=key.descending)
        return matching

    def _consume_bulk_failure(self, record_id: str) -> bool:
        if record_id not in self._failing_bulk_ids:
            return False
        remaining = self._failing_bulk_ids[record_id]
        if remaining is not None:
            if remaining <= 1:
                del self._failing_bulk_ids[record_id]
            else:
                self._failing_bulk_ids[record_id] = remaining - 1
        return True

    def _write(self, record_id: str, body: Mapping[str, Any]) -> Written:
        entry = _Entry(source=copy.deepcopy(dict(body)), seq_no=self._next_seq_no)
        self._next_seq_no += 1
        self._records[record_id] = entry
        return Written(seq_no=entry.seq_no, primary_term=PRIMARY_TERM)

    @staticmethod
    def _to_stored(record_id: str, entry: _Entry) -> StoredRecord:
        return StoredRecord(
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


def _sort_function(key: SortKey) -> Callable[[StoredRecord], tuple[bool, Any]]:
    """値のない記録は、昇順でも降順でも末尾に置く(OpenSearch の `missing: _last` と同じ)。"""

    def sort_value(record: StoredRecord) -> tuple[bool, Any]:
        value = record.source.get(key.field_name)
        is_missing = value is None
        # 降順は `reverse=True` で並べるため、値なしが先頭に来ないよう先頭の要素を反転する。
        return (is_missing != key.descending, 0 if is_missing else value)

    return sort_value
