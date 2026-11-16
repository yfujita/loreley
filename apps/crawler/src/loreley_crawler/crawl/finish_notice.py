"""終了通知の内容(architecture 7.5。確定: CA-K-6)。

内容は、最初の送信の前に組み立てて `finish_notice`(ジョブ記録)に保存して固定し、再送では常に
この内容をそのまま送る(`finished_at` を含む)。変わると Indexer が 409
`finish_content_mismatch` にする。

- `enumeration_completed`: `enumerated_count`・`skipped_document_ids`・`oversize_document_ids`・
  `finished_at`。Indexer が `enumerated_count == N_seen + E_missing` のときだけ削除を判断する
  (件数照合。7.5)。**削除の判断のきっかけになる通知**で、送る条件は呼び出し側が守る
- `failed`・`cancelled`: `outcome`・`source_id`・`finished_at` だけ(Indexer は省略を受理し、
  ID 一覧は保存しない。7.5)

ジョブ記録の `finish_notice` は `{"content": 送る本文, "send_started_at": 時刻 | null}`。
`send_started_at` は `enumeration_completed` の初回の送信を始める直前の時刻で、取り消しが有効かの
境界に使う(4.7)。`failed`・`cancelled` の通知は、これを記録しない(境界に当たらない)。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from loreley_crawler.common.timestamps import format_instant, parse_instant
from loreley_crawler.infrastructure.indexer_client import FinishOutcome


def fixed_instant(now: datetime) -> datetime:
    """ジョブ記録の文字列と、送る値が完全に同じになる時刻(ミリ秒精度)。"""
    return parse_instant(format_instant(now))


@dataclass(frozen=True)
class FinishNotice:
    outcome: FinishOutcome
    finished_at: datetime
    enumerated_count: int | None = None
    skipped_document_ids: tuple[str, ...] | None = None
    oversize_document_ids: tuple[str, ...] | None = None

    @classmethod
    def enumeration_completed(
        cls,
        *,
        now: datetime,
        enumerated_count: int,
        skipped_document_ids: tuple[str, ...],
        oversize_document_ids: tuple[str, ...],
    ) -> "FinishNotice":
        return cls(
            FinishOutcome.ENUMERATION_COMPLETED,
            fixed_instant(now),
            enumerated_count,
            skipped_document_ids,
            oversize_document_ids,
        )

    @classmethod
    def without_counts(cls, outcome: FinishOutcome, *, now: datetime) -> "FinishNotice":
        """`failed`・`cancelled`。件数と ID 一覧は送らない。"""
        if outcome is FinishOutcome.ENUMERATION_COMPLETED:
            raise ValueError("enumeration_completed carries the counts")
        return cls(outcome, fixed_instant(now))

    def content_record(self, source_id: str) -> dict[str, Any]:
        """送る本文(JSON の型。ID 一覧はリスト)。"""
        content: dict[str, Any] = {
            "source_id": source_id,
            "outcome": self.outcome.value,
            "finished_at": format_instant(self.finished_at),
        }
        if self.enumerated_count is not None:
            content["enumerated_count"] = self.enumerated_count
        if self.skipped_document_ids is not None:
            content["skipped_document_ids"] = list(self.skipped_document_ids)
        if self.oversize_document_ids is not None:
            content["oversize_document_ids"] = list(self.oversize_document_ids)
        return content

    def to_record(self, source_id: str, *, send_started_at: datetime | None) -> dict[str, Any]:
        """ジョブ記録の `finish_notice`。"""
        return {
            "content": self.content_record(source_id),
            "send_started_at": None if send_started_at is None else format_instant(send_started_at),
        }
