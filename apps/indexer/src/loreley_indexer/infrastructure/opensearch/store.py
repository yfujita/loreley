"""Store 層の窓口(arch 3.5)。OpenSearch を KVS のように使い、用途ごとの索引を ID で読み書きする。

インターフェースは、ID による取得・保存・削除、単純な条件での一覧、
条件付き更新(楽観的排他制御)に限る。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from loreley_indexer.infrastructure.opensearch.queries import RecordFilter, SortKey
from loreley_indexer.infrastructure.opensearch.results import (
    DeleteOutcome,
    StoredDocument,
    WriteOutcome,
)

LIST_MAX_SIZE = 10_000  # OpenSearch の `max_result_window` の既定値。


class StoreReader(ABC):
    @abstractmethod
    def fetch(self, record_id: str) -> StoredDocument | None:
        pass

    @abstractmethod
    def list_records(
        self, record_filter: RecordFilter, sort: Sequence[SortKey], *, limit: int
    ) -> list[StoredDocument]:
        """条件に合う記録を、直前の書き込みを含む最新の状態で最大 `limit` 件返す。

        `limit` は 1 以上 `LIST_MAX_SIZE` 以下。
        """


class StoreRepository(StoreReader):
    @abstractmethod
    def save(self, record_id: str, body: Mapping[str, Any]) -> WriteOutcome:
        """無条件の保存(置き換え)。"""

    @abstractmethod
    def replace_if_unchanged(
        self, record_id: str, body: Mapping[str, Any], *, seq_no: int, primary_term: int
    ) -> WriteOutcome:
        """読んだ版を条件にした置き換え。"""

    @abstractmethod
    def delete(self, record_id: str) -> DeleteOutcome:
        pass
