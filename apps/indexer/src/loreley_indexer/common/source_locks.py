"""ソース単位の直列化(arch 8章、9.9、plan 案19)。

同じソースの処理を 1 つずつ実行する。Crawler がタイムアウトして再送しても、前の要請の処理と
並行しない。用途ごとに別のインスタンスを作る(別のロック。互いを待たせない):
- `documents`: `documents:batch` と `last-seen`
- `crawl_runs`: 開始通知と終了通知の受理
`documents` と `crawl_runs` は互いに依存できない(R3)ため、共通部品としてここに置く。
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class SourceLocks:
    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    @contextmanager
    def hold(self, source_id: str) -> Iterator[None]:
        with self._lock_for(source_id):
            yield

    def _lock_for(self, source_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(source_id, threading.Lock())
