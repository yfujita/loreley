"""削除バッチと、ソース削除の要請を直列化するソース単位の排他(arch 9.8、9.14。P29)。

ソース削除1(破棄)は、実行中のバッチの完了直後、次のバッチの前確認より前に `discarded` を書き、
応答の時点でそのソースの削除バッチが動いていないことを保証する。そのため、バッチ 1 回分
(前確認から削除まで)と、ソース削除の処理を同じ排他で直列化する。

`lifecycle` の開始・終了通知の直列化(`common.SourceLocks`)とは別のロック。互いを待たせない
(通知は削除バッチの完了を待たずに即時に受理する。arch 9.5)。

ソース削除の要請は最優先にする。ソース削除が待っている間は、削除側が同じソースの次のバッチを
先に取らない。ふつうの排他だと、バッチを終えた削除側がすぐ次のバッチで再取得し、待っている
ソース削除が後回しにされうる(`threading.Lock` は順番を保証しない)ため。
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class SourceBatchExclusion:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._held_sources: set[str] = set()
        self._priority_waiters: dict[str, int] = {}

    @contextmanager
    def hold_batch(self, source_id: str) -> Iterator[None]:
        """削除ワーカーが、バッチ 1 回分(前確認から文書の削除まで)を実行する間、保持する。

        ソース削除が待っている間は取得できない(ソース削除を先に通す)。
        """
        with self._condition:
            self._condition.wait_for(
                lambda: (
                    source_id not in self._held_sources and source_id not in self._priority_waiters
                )
            )
            self._held_sources.add(source_id)
        try:
            yield
        finally:
            self._release(source_id)

    @contextmanager
    def hold_priority(self, source_id: str) -> Iterator[None]:
        """ソース削除の処理の間、保持する。実行中のバッチが終わりしだい、最優先で取得する。"""
        with self._condition:
            self._priority_waiters[source_id] = self._priority_waiters.get(source_id, 0) + 1
            try:
                self._condition.wait_for(lambda: source_id not in self._held_sources)
                self._held_sources.add(source_id)
            finally:
                self._priority_waiters[source_id] -= 1
                if self._priority_waiters[source_id] == 0:
                    del self._priority_waiters[source_id]
        try:
            yield
        finally:
            self._release(source_id)

    def _release(self, source_id: str) -> None:
        with self._condition:
            self._held_sources.discard(source_id)
            self._condition.notify_all()
