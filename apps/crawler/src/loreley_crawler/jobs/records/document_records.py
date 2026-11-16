"""スキップ記録・原本サイズ超過記録の形式と書き込み(architecture 3.3.3・3.3.4・6.4・6.5)。

どちらも `loreley-jobs` の記録で、文書ごと(`document_id` は interface 5.2 の算出値)に 1 件。
ID は `skip-{source_id}-{document_id}`・`oversize-{source_id}-{document_id}`。
本文・秘密情報は書かない(`reason` などの文字列は、呼び出し側が固定文・分類名を渡す)。

書き込みは「なければ `create`、あれば読んだ版を条件にした置き換え」。同じジョブが同じ文書を
再び書いたとき(応答が失われた後のリトライ)は、すでに記録済みとして何もしない
(`consecutive_skips` を二重に増やさないため。0007 §4-3)。競合は読み直してやり直し、
解けなければ `StoreUnavailableError`。
"""

from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Any

from loreley_crawler.common.clock import Clock
from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.common.timestamps import format_instant
from loreley_crawler.infrastructure.opensearch import Repository, Written

# 競合を読み直してやり直す回数(仮値。書き手は Job Runner だけなので、通常は競合しない)。
MAX_WRITE_ATTEMPTS = 3


class DocumentRecordType(StrEnum):
    """`loreley-jobs` の `record_type` のうち、文書ごとの記録。全件走査は 1 種類ずつ行う。"""

    SKIP = "skip"
    OVERSIZE = "oversize"


class SkipStage(StrEnum):
    FETCH = "fetch"
    INDEX = "index"


class OversizeDetector(StrEnum):
    CRAWLER = "crawler"
    INDEXER = "indexer"


def document_record_id(record_type: DocumentRecordType, source_id: str, document_id: str) -> str:
    return f"{record_type.value}-{source_id}-{document_id}"


class DocumentRecordStore:
    def __init__(self, repository: Repository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    def record_skip(
        self,
        *,
        job_id: str,
        source_id: str,
        document_id: str,
        external_id: str,
        stage: SkipStage,
        reason: str,
        attempts: int,
    ) -> None:
        """文書をスキップしたときの記録。なければ作り、あれば試行・段階・理由・日時・ジョブを更新して
        `consecutive_skips` を 1 増やす。"""
        now = format_instant(self._clock.now())

        def create_fields() -> dict[str, Any]:
            return {
                "record_type": DocumentRecordType.SKIP.value,
                "source_id": source_id,
                "document_id": document_id,
                "external_id": external_id,
                "stage": stage.value,
                "reason": reason,
                "attempts": attempts,
                "consecutive_skips": 1,
                "first_skipped_at": now,
                "last_skipped_at": now,
                "last_job_id": job_id,
            }

        def updated_fields(existing: Mapping[str, Any]) -> dict[str, Any]:
            previous_skips = existing.get("consecutive_skips")
            return {
                **existing,
                "stage": stage.value,
                "reason": reason,
                "attempts": attempts,
                "consecutive_skips": (previous_skips if type(previous_skips) is int else 0) + 1,
                "last_skipped_at": now,
                "last_job_id": job_id,
            }

        self._upsert(
            document_record_id(DocumentRecordType.SKIP, source_id, document_id),
            job_id,
            create_fields,
            updated_fields,
        )

    def record_oversize(
        self,
        *,
        job_id: str,
        source_id: str,
        document_id: str,
        external_id: str,
        detected_by: OversizeDetector,
        size: int | None,
    ) -> None:
        """原本サイズ超過の記録。`size` は分かる場合だけ(`size_hint` か申告値)。"""
        now = format_instant(self._clock.now())

        def create_fields() -> dict[str, Any]:
            return {
                "record_type": DocumentRecordType.OVERSIZE.value,
                "source_id": source_id,
                "document_id": document_id,
                "external_id": external_id,
                "detected_by": detected_by.value,
                "size": size,
                "first_detected_at": now,
                "last_detected_at": now,
                "last_job_id": job_id,
            }

        def updated_fields(existing: Mapping[str, Any]) -> dict[str, Any]:
            return {
                **existing,
                "detected_by": detected_by.value,
                "size": size,
                "last_detected_at": now,
                "last_job_id": job_id,
            }

        self._upsert(
            document_record_id(DocumentRecordType.OVERSIZE, source_id, document_id),
            job_id,
            create_fields,
            updated_fields,
        )

    def _upsert(
        self,
        record_id: str,
        job_id: str,
        create_fields: Callable[[], dict[str, Any]],
        updated_fields: Callable[[Mapping[str, Any]], dict[str, Any]],
    ) -> None:
        for _ in range(MAX_WRITE_ATTEMPTS):
            stored = self._repository.fetch(record_id)
            if stored is None:
                if isinstance(self._repository.create(record_id, create_fields()), Written):
                    return
                continue  # `AlreadyExists`。読み直してから更新する
            if stored.source.get("last_job_id") == job_id:
                return  # このジョブがすでに書いた(応答が失われた後のリトライ)
            outcome = self._repository.replace_if_unchanged(
                record_id,
                updated_fields(stored.source),
                seq_no=stored.seq_no,
                primary_term=stored.primary_term,
            )
            if isinstance(outcome, Written):
                return
            # 版の不一致。読み直してやり直す。
        raise StoreUnavailableError("document_record_write_contention")
