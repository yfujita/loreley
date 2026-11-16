"""書き込みは成功するが、応答が失われる(タイムアウト・接続断)Repository の fake。

呼び出し側は `StoreUnavailableError` を受けてリトライする。そのとき、最初の書き込みはすでに成功して
いるので、リトライは `AlreadyExists`(`create`)や `Conflict`(版条件つきの書き込み・削除)になる。
申し送り(0007 §4-3): 呼び出し側は、これを「他者に取られた」と取り違えず、読み直して自分の書き込みか
確かめる。`behavior.inject` は操作を実行せずに応答を差し替えるので、この再現には使えない。

再現できないこと(必要なテストは別の手段で補う):
- 書き込みが**適用されないまま**応答が失われる場合(リトライは通常どおり成功する)。
  `behavior.inject(..., StoreUnavailableError)` を使う(操作を実行せずに例外を送出する)。
- 書き込みの適用が**遅れる**場合(応答が失われた後、リトライの間にも他の書き込みが入る)。この fake は
  すぐに適用する。間に別の書き込みを入れるなら `behavior.before` か `seed` で差し込む。
- `delete_ids`(バルク削除)の応答喪失。`create`・`replace_if_unchanged`・`delete_if_unchanged`
  だけが対象。バルク削除は冪等(存在しない ID は成功)なので、部分失敗は
  `fail_bulk_delete_of` で再現する。
"""

import threading
from collections import Counter
from collections.abc import Mapping
from typing import Any

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.infrastructure.opensearch import (
    CreateOutcome,
    DeleteOutcome,
    ReplaceOutcome,
)
from tests.fakes import in_memory_repository as ops
from tests.fakes.in_memory_repository import InMemoryRepository


class LostResponseRepository(InMemoryRepository):
    def __init__(self) -> None:
        super().__init__()
        self._pending_losses: Counter[str] = Counter()
        self._losses_lock = threading.Lock()

    def lose_response_of(self, operation: str, *, times: int = 1) -> None:
        """次の `times` 回の `operation`(`ops.CREATE` など)を実行し、応答を失わせる。"""
        with self._losses_lock:
            self._pending_losses[operation] += times

    def create(self, record_id: str, body: Mapping[str, Any]) -> CreateOutcome:
        outcome = super().create(record_id, body)
        self._lose_if_scheduled(ops.CREATE)
        return outcome

    def replace_if_unchanged(
        self, record_id: str, body: Mapping[str, Any], *, seq_no: int, primary_term: int
    ) -> ReplaceOutcome:
        outcome = super().replace_if_unchanged(
            record_id, body, seq_no=seq_no, primary_term=primary_term
        )
        self._lose_if_scheduled(ops.REPLACE)
        return outcome

    def delete_if_unchanged(
        self, record_id: str, *, seq_no: int, primary_term: int
    ) -> DeleteOutcome:
        outcome = super().delete_if_unchanged(record_id, seq_no=seq_no, primary_term=primary_term)
        self._lose_if_scheduled(ops.DELETE)
        return outcome

    def _lose_if_scheduled(self, operation: str) -> None:
        with self._losses_lock:
            if self._pending_losses[operation] <= 0:
                return
            self._pending_losses[operation] -= 1
        raise StoreUnavailableError("timeout")
