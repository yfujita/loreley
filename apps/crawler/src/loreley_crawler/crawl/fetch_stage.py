"""文書の取得: リトライ・スキップ・原本サイズ超過(architecture 6.2・6.3・6.5)。

`fetch` の失敗は、interface 6.2 の属性(`retry`)に従う。`transient`・`unknown` はリトライし
(最大試行回数は `common` の設定。Connector は内部でリトライしない)、`permanent` はリトライしない。
- `oversize`: スキップではなく原本サイズ超過として記録する(計数もリセットもしない)
- `fetch_not_found`・`fetch_permission_denied`・`fetch_transient`・`connector_internal_error`:
  その文書をスキップする(`stage=fetch`。取得段階の連続スキップを数える)
- 上記以外の分類(取得が返してはならないもの): Connector の契約違反なので、ジョブを `failed`
  (`internal_error`)にする(削除に関わるため、安全側)

取得に成功したら、取得段階の連続スキップをリセットする。
"""

from loreley_crawler.connectors.interface import ConnectorError, ErrorCategory, RetryHint
from loreley_crawler.crawl.constants import LOCAL_CHECKS
from loreley_crawler.crawl.failure import CrawlFailure
from loreley_crawler.crawl.outcomes import DocumentOutcomeRecorder
from loreley_crawler.crawl.skip_counter import ConsecutiveSkipCounter
from loreley_crawler.documents import DocumentFetcher, EnumeratedDocument, PreparedDocument
from loreley_crawler.jobs import FailureReason, JobContext, OversizeDetector, SkipStage

_SKIPPABLE_FETCH_FAILURES = frozenset(
    {
        ErrorCategory.FETCH_NOT_FOUND,
        ErrorCategory.FETCH_PERMISSION_DENIED,
        ErrorCategory.FETCH_TRANSIENT,
        ErrorCategory.CONNECTOR_INTERNAL_ERROR,
    }
)


class FetchStage:
    def __init__(
        self,
        *,
        context: JobContext,
        fetcher: DocumentFetcher,
        outcomes: DocumentOutcomeRecorder,
        skip_counter: ConsecutiveSkipCounter,
    ) -> None:
        self._context = context
        self._fetcher = fetcher
        self._outcomes = outcomes
        self._skip_counter = skip_counter

    def fetch(self, document: EnumeratedDocument) -> PreparedDocument | None:
        """原本を取得する。スキップ・原本サイズ超過にしたときは None。

        確認点(所有・取り消し)は、取得の各試行の前に通る。文書の区切りの確認を兼ねる。
        """
        attempts = 0

        def fetch_once() -> PreparedDocument:
            nonlocal attempts
            attempts += 1
            return self._fetcher.fetch(document.ref)

        try:
            prepared = self._context.retrier(LOCAL_CHECKS).run(
                fetch_once, is_retryable_error=_is_retryable_fetch_failure
            )
        except ConnectorError as error:
            self._handle_failure(document, error, attempts)
            return None
        self._skip_counter.record_success(SkipStage.FETCH)
        return prepared

    def _handle_failure(
        self, document: EnumeratedDocument, error: ConnectorError, attempts: int
    ) -> None:
        if error.category is ErrorCategory.OVERSIZE:
            self._outcomes.record_oversize(
                document, detected_by=OversizeDetector.CRAWLER, size=document.ref.size_hint
            )
            return
        if error.category not in _SKIPPABLE_FETCH_FAILURES:
            raise CrawlFailure(
                FailureReason.INTERNAL_ERROR,
                f"Connector が取得で契約外の分類を返した: {error.category.value}",
            ) from None
        self._outcomes.record_skip(
            document, stage=SkipStage.FETCH, failure_name=error.category.value, attempts=attempts
        )


def _is_retryable_fetch_failure(error: Exception) -> bool:
    return (
        isinstance(error, ConnectorError)
        and error.category in _SKIPPABLE_FETCH_FAILURES
        and error.retry is not RetryHint.PERMANENT
    )
