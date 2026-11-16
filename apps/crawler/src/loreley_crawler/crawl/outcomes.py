"""文書ごとの結果(スキップ・原本サイズ超過)の記録と計数(architecture 6.2〜6.5)。

スキップ記録・原本サイズ超過記録の書き込み(`jobs` のファサード経由)と、件数照合のための ID 集合・
連続スキップの計数を、1 か所で行う。取得段階と登録段階が同じ規則を使う。
"""

from loreley_crawler.crawl.constants import LOCAL_CHECKS
from loreley_crawler.crawl.failure import CrawlFailure
from loreley_crawler.crawl.skip_counter import ConsecutiveSkipCounter
from loreley_crawler.crawl.tally import RegistrationTally
from loreley_crawler.documents import EnumeratedDocument
from loreley_crawler.jobs import (
    DocumentRecords,
    FailureReason,
    JobContext,
    OversizeDetector,
    SkipStage,
)

# スキップ記録の `reason`: 失敗の分類名と短い固定文(architecture 3.3.3)。Connector・Indexer の
# 説明文(`message`)は載せない。
_SKIP_REASON_TEXTS = {
    "fetch_not_found": "取得時に文書が見つからなかった",
    "fetch_permission_denied": "取得の権限がなかった",
    "fetch_transient": "取得の一時的な失敗が続いた",
    "connector_internal_error": "Connector の想定外の例外",
    "document_rejected": "Indexer が文書を拒否した",
}


class DocumentOutcomeRecorder:
    def __init__(
        self,
        *,
        context: JobContext,
        source_id: str,
        document_records: DocumentRecords,
        tally: RegistrationTally,
        skip_counter: ConsecutiveSkipCounter,
    ) -> None:
        self._context = context
        self._source_id = source_id
        self._document_records = document_records
        self._tally = tally
        self._skip_counter = skip_counter

    def record_skip(
        self, document: EnumeratedDocument, *, stage: SkipStage, failure_name: str, attempts: int
    ) -> None:
        """文書をスキップする。連続が規定の件数に達したら `CrawlFailure`(`skip_limit_exceeded`)。

        `failure_name` は失敗の分類名(interface 6.2)か Indexer の失敗種別名。
        """
        self._document_records.record_skip(
            job_id=self._context.job_id,
            source_id=self._source_id,
            document_id=document.document_id,
            external_id=document.external_id,
            stage=stage,
            reason=_skip_reason(failure_name),
            attempts=attempts,
            retrier=self._context.retrier(LOCAL_CHECKS),
        )
        self._tally.record_skipped(document.document_id)
        if self._skip_counter.record_skip(stage):
            raise CrawlFailure(
                FailureReason.SKIP_LIMIT_EXCEEDED,
                f"{stage.value} 段階で連続 {self._skip_counter.limit} 件スキップした"
                f"(直近の失敗: {failure_name})",
            )

    def record_oversize(
        self, document: EnumeratedDocument, *, detected_by: OversizeDetector, size: int | None
    ) -> None:
        """原本サイズ超過を記録する。スキップではなく、計数もリセットもしない(6.3・6.5)。"""
        self._document_records.record_oversize(
            job_id=self._context.job_id,
            source_id=self._source_id,
            document_id=document.document_id,
            external_id=document.external_id,
            detected_by=detected_by,
            size=size,
            retrier=self._context.retrier(LOCAL_CHECKS),
        )
        self._tally.record_oversize(document.document_id)


def _skip_reason(failure_name: str) -> str:
    text = _SKIP_REASON_TEXTS.get(failure_name)
    return failure_name if text is None else f"{failure_name}: {text}"
