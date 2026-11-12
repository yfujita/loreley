"""要約の生成依頼キュー(有界。arch 7.2、K39)。

依頼は文書 ID だけを持つ。ワーカーが生成を始めるときに文書を読み直して本文とハッシュを取る
(arch 7.4「生成を始めた時点の文書」)ため、キューに本文を溜めずメモリが有界に保たれ、
登録からの依頼と再走査からの依頼を同じ処理で扱える。
"""

import threading
from collections import deque
from enum import StrEnum


class SubmitResult(StrEnum):
    ACCEPTED = "accepted"
    ALREADY_QUEUED = "already_queued"  # 待機中の依頼は、生成を始めるときに最新の文書を読む
    FULL = "full"  # 受け付けない。`pending` のまま再走査に委ねる


class SummaryRequestQueue:
    def __init__(self, max_size: int) -> None:
        if max_size < 1:
            raise ValueError("max_size must be at least 1")
        self._max_size = max_size
        self._condition = threading.Condition()
        self._waiting: deque[str] = deque()
        self._waiting_ids: set[str] = set()
        self._overflowed = False
        self._closed = False

    def submit(self, document_id: str) -> SubmitResult:
        with self._condition:
            if document_id in self._waiting_ids:
                return SubmitResult.ALREADY_QUEUED
            if len(self._waiting) >= self._max_size:
                self._overflowed = True
                return SubmitResult.FULL
            self._waiting.append(document_id)
            self._waiting_ids.add(document_id)
            self._condition.notify()
            return SubmitResult.ACCEPTED

    def take(self, wait_seconds: float = 0.0) -> str | None:
        """先頭の依頼を取り出す。空なら `wait_seconds` まで待ち、それでも空なら None。"""
        with self._condition:
            if not self._waiting and wait_seconds > 0 and not self._closed:
                self._condition.wait_for(
                    lambda: bool(self._waiting) or self._closed, timeout=wait_seconds
                )
            if not self._waiting:
                return None
            document_id = self._waiting.popleft()
            self._waiting_ids.discard(document_id)
            return document_id

    def take_overflow_flag(self) -> bool:
        """満杯で依頼を断ったことがあれば True を返し、記録を消す。"""
        with self._condition:
            overflowed = self._overflowed
            self._overflowed = False
            return overflowed

    def close(self) -> None:
        """待っているワーカーを起こす。以後 `take` は待たない。"""
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def __len__(self) -> int:
        with self._condition:
            return len(self._waiting)
