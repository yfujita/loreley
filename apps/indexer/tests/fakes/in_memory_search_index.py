"""検索インデックスのインメモリ fake。

設計書の理解を再現したもので、実機の OpenSearch と食い違う可能性がある(U-31)。再現するもの:
- `_seq_no`・`_primary_term` による楽観ロック、`op_type=create` の競合
- ID 取得(リアルタイム)と、検索・件数(`refresh` するまで反映されない)の違い
- `delete_by_query` の `conflicts=proceed`(検索時点から文書が変わっていれば、競合として飛ばす)
- `last_seen_at` の max 比較 Update
- 割り込みフック・応答の差し替え(`FakeBehavior`)
"""

import copy
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from loreley_indexer.common.timestamps import format_instant, parse_instant
from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    DeleteByQueryResult,
    Deleted,
    DeleteOutcome,
    DocumentFilter,
    LastSeenOutcome,
    NotFound,
    SearchIndexRepository,
    StoredDocument,
    Unchanged,
    Updated,
    WriteOutcome,
    Written,
)
from loreley_indexer.infrastructure.opensearch.search_index_adapter import (
    FETCH_FOR_DELETION_FIELDS,
)
from tests.fakes.behavior import FakeBehavior

PRIMARY_TERM = 1

FETCH = "fetch"
FETCH_FOR_DELETION = "fetch_for_deletion"
CREATE = "create"
REPLACE = "replace_if_unchanged"
RAISE_LAST_SEEN_AT = "raise_last_seen_at"
DELETE = "delete_if_unchanged"
SEARCH_IDS = "search_document_ids"
COUNT = "count"
COUNT_EXISTING_IDS = "count_existing_ids"
REFRESH = "refresh"
DELETE_BY_QUERY = "delete_by_query"
WRITE_OPERATIONS = (CREATE, REPLACE, RAISE_LAST_SEEN_AT, DELETE, DELETE_BY_QUERY)


@dataclass
class _Entry:
    source: dict[str, Any]
    seq_no: int


class InMemorySearchIndex(SearchIndexRepository):
    def __init__(
        self,
        *,
        refresh_on_write: bool = False,
        missing_document_conditional_write: Literal["not_found", "conflict"] = "not_found",
    ) -> None:
        """
        refresh_on_write: 書き込みのたびに検索へ反映する。False なら `refresh()` まで反映しない。
        missing_document_conditional_write: 存在しない文書への `if_seq_no` 付き書き込みの応答。
            実機の挙動は未確認(arch U-31(2))のため、どちらも再現できるようにしてある。
        """
        self.behavior = FakeBehavior()
        # 各操作の本体(フック・差し替えの後)を直列にする。実機の文書単位の原子性に相当し、
        # 複数スレッドが同じ版で書いたとき、成功するのは 1 つだけになる。
        # フックと Gate はロックの外で動く(中でブロックしても他スレッドを止めないため)。
        self._lock = threading.RLock()
        self.refresh_stalled = False  # True の間、`refresh()` は何も反映しない(D-90(b))
        self._refresh_on_write = refresh_on_write
        self._missing_outcome = (
            NotFound() if missing_document_conditional_write == "not_found" else Conflict()
        )
        self._documents: dict[str, _Entry] = {}
        self._searchable: dict[str, _Entry] = {}
        self._next_seq_no = 0

    # --- SearchIndexRepository ---

    def fetch(self, document_id: str) -> StoredDocument | None:
        if (intercepted := self.behavior.enter(FETCH, document_id)) is not None:
            return intercepted.value
        with self._lock:
            entry = self._documents.get(document_id)
            if entry is None:
                return None
            return StoredDocument(
                id=document_id,
                source=copy.deepcopy(entry.source),
                seq_no=entry.seq_no,
                primary_term=PRIMARY_TERM,
            )

    def fetch_for_deletion(self, document_id: str) -> StoredDocument | None:
        if (intercepted := self.behavior.enter(FETCH_FOR_DELETION, document_id)) is not None:
            return intercepted.value
        with self._lock:
            entry = self._documents.get(document_id)
            if entry is None:
                return None
            return StoredDocument(
                id=document_id,
                source={
                    name: copy.deepcopy(entry.source[name])
                    for name in FETCH_FOR_DELETION_FIELDS
                    if name in entry.source
                },
                seq_no=entry.seq_no,
                primary_term=PRIMARY_TERM,
            )

    def create(self, document_id: str, source: Mapping[str, Any]) -> WriteOutcome:
        if (intercepted := self.behavior.enter(CREATE, document_id)) is not None:
            return intercepted.value
        with self._lock:
            if document_id in self._documents:
                return Conflict()
            return self._write(document_id, source)

    def replace_if_unchanged(
        self, document_id: str, source: Mapping[str, Any], *, seq_no: int, primary_term: int
    ) -> WriteOutcome:
        if (intercepted := self.behavior.enter(REPLACE, document_id)) is not None:
            return intercepted.value
        with self._lock:
            entry = self._documents.get(document_id)
            if entry is None:
                return self._missing_outcome
            if entry.seq_no != seq_no or primary_term != PRIMARY_TERM:
                return Conflict()
            return self._write(document_id, source)

    def raise_last_seen_at(self, document_id: str, last_seen_at: datetime) -> LastSeenOutcome:
        if (intercepted := self.behavior.enter(RAISE_LAST_SEEN_AT, document_id)) is not None:
            return intercepted.value
        with self._lock:
            entry = self._documents.get(document_id)
            if entry is None:
                return NotFound()
            current = entry.source.get("last_seen_at")
            if current is not None and parse_instant(current) >= last_seen_at:
                return Unchanged()
            updated_source = {**entry.source, "last_seen_at": format_instant(last_seen_at)}
            self._write(document_id, updated_source)
            return Updated()

    def delete_if_unchanged(
        self, document_id: str, *, seq_no: int, primary_term: int
    ) -> DeleteOutcome:
        if (intercepted := self.behavior.enter(DELETE, document_id)) is not None:
            return intercepted.value
        with self._lock:
            entry = self._documents.get(document_id)
            if entry is None:
                return self._missing_outcome
            if entry.seq_no != seq_no or primary_term != PRIMARY_TERM:
                return Conflict()
            self._remove(document_id)
            return Deleted()

    def search_document_ids(
        self, document_filter: DocumentFilter, *, page_size: int, after: str | None
    ) -> list[str]:
        if (intercepted := self.behavior.enter(SEARCH_IDS)) is not None:
            return intercepted.value
        with self._lock:
            matching_ids = sorted(
                document_id
                for document_id, entry in self._searchable.items()
                if _matches(document_filter, entry.source)
                and (after is None or document_id > after)
            )
        return matching_ids[:page_size]

    def count(self, document_filter: DocumentFilter) -> int:
        if (intercepted := self.behavior.enter(COUNT)) is not None:
            return intercepted.value
        with self._lock:
            return sum(
                1 for entry in self._searchable.values() if _matches(document_filter, entry.source)
            )

    def count_existing_ids(self, document_ids: Sequence[str]) -> int:
        """指定した ID のうち、検索で見える文書の数。

        前提: `document_ids` に重複がないこと。fake は重複を 1 件に数えるが、実アダプタは
        1000 件ずつに分けて合算するため、チャンクをまたぐ重複は 2 回数えうる。
        呼び出し側が重複を渡さないことで、両者の結果をそろえる。
        """
        if (intercepted := self.behavior.enter(COUNT_EXISTING_IDS)) is not None:
            return intercepted.value
        with self._lock:
            return sum(1 for document_id in set(document_ids) if document_id in self._searchable)

    def refresh(self) -> None:
        if self.behavior.enter(REFRESH) is not None:
            return
        with self._lock:
            if self.refresh_stalled:
                return
            self._searchable = copy.deepcopy(self._documents)

    def delete_by_query(self, document_filter: DocumentFilter) -> DeleteByQueryResult:
        if document_filter.source_id is None:
            raise ValueError("delete_by_query requires source_id")
        if (intercepted := self.behavior.enter(DELETE_BY_QUERY)) is not None:
            return intercepted.value
        with self._lock:
            deleted = 0
            version_conflicts = 0
            for document_id, searched in list(self._searchable.items()):
                if not _matches(document_filter, searched.source):
                    continue
                current = self._documents.get(document_id)
                if current is None or current.seq_no != searched.seq_no:
                    version_conflicts += 1
                    continue
                self._remove(document_id)
                deleted += 1
        return DeleteByQueryResult(
            deleted=deleted, version_conflicts=version_conflicts, failure_count=0
        )

    # --- テストの準備・確認用(フックを通らず、呼び出しとして記録されない) ---

    def seed(
        self, document_id: str, source: Mapping[str, Any], *, searchable: bool = True
    ) -> StoredDocument:
        """文書を直接置く。別の書き手による書き込みの再現にも使う(seq_no が進む)。"""
        with self._lock:
            written = self._write(document_id, source, force_searchable=searchable)
        return StoredDocument(
            id=document_id,
            source=copy.deepcopy(dict(source)),
            seq_no=written.seq_no,
            primary_term=PRIMARY_TERM,
        )

    def seed_removal(self, document_id: str) -> None:
        """別の書き手による削除の再現。"""
        with self._lock:
            self._remove(document_id)

    def source_of(self, document_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._documents.get(document_id)
            return copy.deepcopy(entry.source) if entry is not None else None

    def document_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._documents)

    def write_calls(self) -> list[str]:
        """書き込み系の呼び出しの記録(「1 件も書かない」の確認に使う)。"""
        return [call.operation for call in self.behavior.calls_of(*WRITE_OPERATIONS)]

    # --- 内部(呼び出し側が `_lock` を持っていること) ---

    def _write(
        self, document_id: str, source: Mapping[str, Any], *, force_searchable: bool = False
    ) -> Written:
        created = document_id not in self._documents
        entry = _Entry(source=copy.deepcopy(dict(source)), seq_no=self._next_seq_no)
        self._next_seq_no += 1
        self._documents[document_id] = entry
        if self._refresh_on_write or force_searchable:
            self._searchable[document_id] = copy.deepcopy(entry)
        return Written(seq_no=entry.seq_no, primary_term=PRIMARY_TERM, created=created)

    def _remove(self, document_id: str) -> None:
        self._documents.pop(document_id, None)
        self._next_seq_no += 1  # 削除も操作として seq_no を消費する
        if self._refresh_on_write:
            self._searchable.pop(document_id, None)


def _matches(document_filter: DocumentFilter, source: Mapping[str, Any]) -> bool:
    if (
        document_filter.source_id is not None
        and source.get("source_id") != document_filter.source_id
    ):
        return False
    if (
        document_filter.summary_status is not None
        and source.get("summary_status") != document_filter.summary_status
    ):
        return False
    if document_filter.last_seen_at_gte is None and document_filter.last_seen_at_lt is None:
        return True
    last_seen_at = source.get("last_seen_at")
    if last_seen_at is None:
        return False
    last_seen = parse_instant(last_seen_at)
    if (
        document_filter.last_seen_at_gte is not None
        and last_seen < document_filter.last_seen_at_gte
    ):
        return False
    return not (
        document_filter.last_seen_at_lt is not None and last_seen >= document_filter.last_seen_at_lt
    )
