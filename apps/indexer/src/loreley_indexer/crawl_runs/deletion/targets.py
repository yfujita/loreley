"""削除対象の ID の取り込み(arch 9.8 バッチの流れ(1)、K47)。"""

from collections.abc import Collection
from datetime import datetime

from loreley_indexer.infrastructure.opensearch import DocumentFilter, SearchIndexRepository


class TargetLimitExceeded(Exception):
    """削除対象が `max_deletion_targets` を超えた。メモリを無制限に使わないため、削除しない。"""


class TargetCollector:
    def __init__(
        self, search_index: SearchIndexRepository, *, page_size: int, max_targets: int
    ) -> None:
        self._search_index = search_index
        self._page_size = page_size
        self._max_targets = max_targets

    def collect(self, *, source_id: str, cutoff: datetime, excluded: Collection[str]) -> list[str]:
        """`last_seen_at < cutoff` の文書の ID を、`document_id` の昇順で全件取り込む。

        呼び出し側が、直前に `refresh()` していること(同じ判定時点・同じ refresh 後。9.3)。
        `excluded`(スキップ文書・サイズ超過文書の ID)は、取り込んだあとにメモリ上で除く
        (アダプタは ID 条件を持たない)。`from`/`size` は使わず、`search_after` で最後まで読む
        (`max_result_window` を超える対象を取りこぼさないため)。
        """
        document_filter = DocumentFilter(source_id=source_id, last_seen_at_lt=cutoff)
        targets: list[str] = []
        after: str | None = None
        while True:
            page = self._search_index.search_document_ids(
                document_filter, page_size=self._page_size, after=after
            )
            for document_id in page:
                if document_id in excluded:
                    continue
                targets.append(document_id)
                if len(targets) > self._max_targets:
                    raise TargetLimitExceeded
            if len(page) < self._page_size:
                return targets
            after = page[-1]
