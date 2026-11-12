"""検索インデックスの窓口(module 4.4)。

検索インデックスは Repository インターフェースの対象外(arch 3.5)で、
文書の取得・書き込み・検索をここから直接行う。
409 のときの読み直しは呼び出し側が行い、ここでは繰り返さない(R8)。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from loreley_indexer.infrastructure.opensearch.queries import DocumentFilter
from loreley_indexer.infrastructure.opensearch.results import (
    DeleteByQueryResult,
    DeleteOutcome,
    LastSeenOutcome,
    StoredDocument,
    WriteOutcome,
)


class SearchIndexRepository(ABC):
    @abstractmethod
    def fetch(self, document_id: str) -> StoredDocument | None:
        """ID で取得する(リアルタイム。`_seq_no`・`_primary_term` つき)。文書がなければ None。"""

    @abstractmethod
    def fetch_for_deletion(self, document_id: str) -> StoredDocument | None:
        """削除の再確認用の取得。`source` は `source_id` と `last_seen_at` だけ(本文を読まない)。

        版(`_seq_no`・`_primary_term`)は `fetch` と同じで、`delete_if_unchanged` に使える。
        文書がなければ None。
        """

    @abstractmethod
    def create(self, document_id: str, source: Mapping[str, Any]) -> WriteOutcome:
        """存在しない場合だけ成功する書き込み(`op_type=create`)。既存なら Conflict。"""

    @abstractmethod
    def replace_if_unchanged(
        self, document_id: str, source: Mapping[str, Any], *, seq_no: int, primary_term: int
    ) -> WriteOutcome:
        """読んだ版を条件にした全文書き込み。読んだあとに更新されていれば Conflict。"""

    @abstractmethod
    def raise_last_seen_at(self, document_id: str, last_seen_at: datetime) -> LastSeenOutcome:
        """`last_seen_at` を max 比較で更新する。現在値以上なら書かない(Unchanged)。

        文書がなければ NotFound(upsert しない)。
        """

    @abstractmethod
    def delete_if_unchanged(
        self, document_id: str, *, seq_no: int, primary_term: int
    ) -> DeleteOutcome:
        """読んだ版を条件にした削除。"""

    @abstractmethod
    def search_document_ids(
        self, document_filter: DocumentFilter, *, page_size: int, after: str | None
    ) -> list[str]:
        """`document_id` の昇順で、`after` より後の ID を最大 `page_size` 件返す(`search_after`)。

        検索なので、直前の書き込みは `refresh` するまで反映されない。
        """

    @abstractmethod
    def count(self, document_filter: DocumentFilter) -> int:
        """条件に合う文書数。検索なので `refresh` 後の状態を数える。"""

    @abstractmethod
    def count_existing_ids(self, document_ids: Sequence[str]) -> int:
        """指定した ID のうち、索引にある文書の数(`refresh` 後の状態)。

        `document_ids` に重複を含めないこと(実装は ID を分割して合算するため、
        分割をまたぐ重複は二重に数えうる)。
        """

    @abstractmethod
    def refresh(self) -> None:
        pass

    @abstractmethod
    def delete_by_query(self, document_filter: DocumentFilter) -> DeleteByQueryResult:
        """`conflicts=proceed` で削除する。競合した文書はその回は飛ばす(R7 の例外)。

        全文書の誤削除を防ぐため、`source_id` の指定を必須とする。
        """
