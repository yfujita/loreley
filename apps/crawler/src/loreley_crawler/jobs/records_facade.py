"""`crawl`・`source_delete` が使う、`loreley-jobs` の記録操作のファサード(module 4.4)。

`crawl`・`source_delete` は R3 により `infrastructure.opensearch`(`Repository`)を import できない。
一方、スキップ記録・原本サイズ超過記録の書き込みと整理、直前に完了したクロールの読み取りは
`Repository` を引数に取る(`jobs/records`)。そこで、`jobs` の入口に `Repository` を内部に束ねた
クラスを置く。`main.py` が `loreley-jobs` 用の Repository で組み立てて注入する。

どの操作も、Store 層全体の異常(`StoreUnavailableError`)は、呼び出し側が渡す `Retrier`(確認点つきで
`JobContext.retrier(...)` から取る)でリトライを尽くしてから送出する。`StoreUnexpectedResponseError`
はリトライせずに伝播する(Crawler の不具合の疑い)。
"""

from collections.abc import Callable

from loreley_crawler.common.clock import Clock
from loreley_crawler.common.errors import is_store_unavailable
from loreley_crawler.common.retry import Retrier
from loreley_crawler.infrastructure.opensearch import Repository
from loreley_crawler.jobs.records import (
    DocumentRecordStore,
    DocumentRecordType,
    OversizeDetector,
    PreviousCrawl,
    SkipStage,
    delete_document_records_of_source,
    find_previous_completed_crawl,
    purge_document_records,
)


class DocumentRecords:
    """スキップ記録・原本サイズ超過記録の書き込みと、整理・一括削除。"""

    def __init__(self, repository: Repository, clock: Clock) -> None:
        self._repository = repository
        self._store = DocumentRecordStore(repository, clock)

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
        retrier: Retrier,
    ) -> None:
        """文書をスキップしたときの記録(architecture 6.4)。同じジョブの再書き込みは何もしない。"""
        retrier.run(
            lambda: self._store.record_skip(
                job_id=job_id,
                source_id=source_id,
                document_id=document_id,
                external_id=external_id,
                stage=stage,
                reason=reason,
                attempts=attempts,
            ),
            is_retryable_error=is_store_unavailable,
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
        retrier: Retrier,
    ) -> None:
        """原本サイズ超過の記録(architecture 6.5)。`size` は分かる場合だけ。"""
        retrier.run(
            lambda: self._store.record_oversize(
                job_id=job_id,
                source_id=source_id,
                document_id=document_id,
                external_id=external_id,
                detected_by=detected_by,
                size=size,
            ),
            is_retryable_error=is_store_unavailable,
        )

    def purge(
        self,
        *,
        source_id: str,
        record_type: DocumentRecordType,
        should_delete: Callable[[str], bool],
        retrier: Retrier,
    ) -> int:
        """そのソースの `record_type` の記録のうち、`should_delete(document_id)` が真のものを消す。

        クロールの最後の整理(architecture 6.4)。`record_type` ごとに 1 回呼ぶ。消した件数を返す。
        バルク削除の部分失敗が尽きたら `StoreWriteFailedError`。
        """
        return purge_document_records(
            self._repository,
            retrier,
            source_id=source_id,
            record_type=record_type,
            should_delete=should_delete,
        )

    def delete_all_of_source(self, *, source_id: str, retrier: Retrier) -> int:
        """そのソースの `skip`・`oversize` の記録をすべて消す(`source_delete` の順 3)。"""
        return delete_document_records_of_source(self._repository, retrier, source_id=source_id)


class JobHistory:
    """過去のジョブ記録の読み取り。"""

    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def find_previous_completed_crawl(
        self, *, source_id: str, excluding_job_id: str, max_jobs: int, retrier: Retrier
    ) -> PreviousCrawl | None:
        """同じソースで直前に列挙を完了した `crawl` ジョブ(0 件列挙の警告用。architecture 7.7)。"""
        return retrier.run(
            lambda: find_previous_completed_crawl(
                self._repository,
                source_id=source_id,
                excluding_job_id=excluding_job_id,
                max_jobs=max_jobs,
            ),
            is_retryable_error=is_store_unavailable,
        )
