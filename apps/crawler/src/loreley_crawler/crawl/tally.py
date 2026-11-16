"""登録結果の集計と、件数照合のための ID 集合(architecture 7.5・7.7。CA-P-31)。

`registration`(ジョブ記録)の項目と、終了通知の `skipped_document_ids`・`oversize_document_ids` の
元になる。永続のスキップ記録・原本サイズ超過記録からは作らず、このクロールの実行状態から作る
(7.5)。

- **再送時の規則**: `document_id` ごとに、最初に受け取れた `status: ok` の結果を保持し、再送の
  結果で数え直さない(`record_registered`)。
- **`partial`**: 集計の途中は True。すべての応答を確認し終えたら `finalize` で False にする。
  False にした後は戻さない(確定前に失敗・取り消しで終わったジョブは True のまま保持する)。
"""

from typing import Any

from loreley_crawler.infrastructure.indexer_client import Change, DocumentRegistered


class RegistrationTally:
    def __init__(self) -> None:
        self._created_count = 0
        self._updated_count = 0
        self._unchanged_count = 0
        self._error_count = 0
        self._invalid_id_count = 0
        self._partial = True
        self._counted_document_ids: set[str] = set()
        # 重複を除き、記録した順(終了通知の ID 一覧を決定的にする)。
        self._skipped_document_ids: dict[str, None] = {}
        self._oversize_document_ids: dict[str, None] = {}

    @property
    def partial(self) -> bool:
        return self._partial

    @property
    def invalid_id_count(self) -> int:
        return self._invalid_id_count

    @property
    def skipped_document_ids(self) -> tuple[str, ...]:
        return tuple(self._skipped_document_ids)

    @property
    def oversize_document_ids(self) -> tuple[str, ...]:
        return tuple(self._oversize_document_ids)

    @property
    def registered_count(self) -> int:
        """Indexer が `status: ok` を返した文書の数(重複なし)。"""
        return len(self._counted_document_ids)

    def is_skipped(self, document_id: str) -> bool:
        return document_id in self._skipped_document_ids

    def is_oversize(self, document_id: str) -> bool:
        return document_id in self._oversize_document_ids

    def record_registered(self, result: DocumentRegistered) -> bool:
        """`status: ok` の結果を数える。すでに数えた文書なら何もせず False(最初の結果を保持)。"""
        if result.document_id in self._counted_document_ids:
            return False
        self._counted_document_ids.add(result.document_id)
        if result.change is Change.CREATED:
            self._created_count += 1
        elif result.change is Change.UPDATED:
            self._updated_count += 1
        else:
            self._unchanged_count += 1
        if result.extract_failed:
            self._error_count += 1
        return True

    def record_skipped(self, document_id: str) -> None:
        self._skipped_document_ids[document_id] = None

    def record_oversize(self, document_id: str) -> None:
        self._oversize_document_ids[document_id] = None

    def record_invalid_id(self) -> None:
        self._invalid_id_count += 1

    def finalize(self) -> None:
        self._partial = False

    def to_record(self, *, enumerated_count: int) -> dict[str, Any]:
        """ジョブ記録の `registration`(JSON の型)。`enumerated_count` は列挙の包みが数えた値。"""
        return {
            "enumerated_count": enumerated_count,
            "created_count": self._created_count,
            "updated_count": self._updated_count,
            "unchanged_count": self._unchanged_count,
            "skipped_count": len(self._skipped_document_ids),
            "oversize_count": len(self._oversize_document_ids),
            "error_count": self._error_count,
            "invalid_id_count": self._invalid_id_count,
            "partial": self._partial,
        }
