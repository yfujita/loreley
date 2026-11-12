"""バッチ登録(`documents:batch`)のドメイン処理(arch 4.3、5章、6章、8章。api 4.3)。

HTTP の形式検証と base64 のデコードは api 層(P5)の責務で、ここは検証済みの入力を受ける。

1 リクエストの流れ:
1. 受理条件(`crawl_runs`)をリクエストの先頭で 1 回確認する。拒否は例外で、1 件も書かない。
2. 文書ごとに、ロック所有確認 → サイズ確認 → メタデータの検査 → 抽出 → 取得 →
   新規・更新・変更なしの判定 → 書き込み。
3. 409 は呼び出し側(ここ)が読み直して再判定する(R8)。上限を超えたら `write_conflict`。

OpenSearch の全体異常(`UnavailableError`)は文書単位の失敗にせず伝播させる(api 層が 503)。
"""

from collections.abc import Mapping, Sequence
from typing import Any

from loreley_indexer.common.clock import Clock
from loreley_indexer.common.source_locks import SourceLocks
from loreley_indexer.crawl_runs import Admission, AdmissionChecker
from loreley_indexer.documents.config import RegistrationConfig
from loreley_indexer.documents.document_id import compute_document_id
from loreley_indexer.documents.extraction import ExtractionFailed, ExtractionResult, TextExtractor
from loreley_indexer.documents.ownership import LockOwnershipChecker
from loreley_indexer.documents.requests import CrawlContext, DocumentInput
from loreley_indexer.documents.results import (
    Change,
    DocumentFailed,
    DocumentOutcome,
    DocumentRegistered,
    FailureType,
)
from loreley_indexer.documents.search_document import (
    build_source,
    is_unchanged,
    last_seen_at_is_behind,
)
from loreley_indexer.documents.summarization import SummaryRequestQueue, SummaryStatus
from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    JobsReader,
    NotFound,
    OpenSearchUnexpectedResponseError,
    Rejected,
    SearchIndexRepository,
    StoredDocument,
    Unchanged,
    Updated,
    Written,
)

_FAILURE_MESSAGES = {
    FailureType.LOCK_NOT_OWNED: "the crawler does not own the source lock",
    FailureType.OVERSIZE: "the raw content exceeds the size limit",
    FailureType.WRITE_CONFLICT: "write conflicts persisted after the reread limit",
    FailureType.UPDATE_CONFLICT: "last_seen_at update conflicts persisted",
    FailureType.DOCUMENT_REJECTED: "the document was rejected",
}


_UNENCODABLE_METADATA_DETAIL = "metadata is not valid Unicode text"


class DocumentRegistrar:
    def __init__(
        self,
        *,
        config: RegistrationConfig,
        admission_checker: AdmissionChecker,
        search_index: SearchIndexRepository,
        jobs: JobsReader,
        extractor: TextExtractor,
        summary_requests: SummaryRequestQueue,
        source_locks: SourceLocks,
        clock: Clock,
    ) -> None:
        self._config = config
        self._admission_checker = admission_checker
        self._search_index = search_index
        self._ownership = LockOwnershipChecker(jobs, clock)
        self._extractor = extractor
        self._summary_requests = summary_requests
        self._source_locks = source_locks
        self._clock = clock

    def register(
        self, context: CrawlContext, documents: Sequence[DocumentInput]
    ) -> list[DocumentOutcome]:
        """文書ごとの結果を、入力と同じ順で返す。

        受理条件を満たさなければ `AdmissionRejectedError` を送出する(1 件も書かない)。
        `source_id`・`external_id` に NUL や孤立サロゲートを含む入力は ValueError
        (api 層が 400 にする)。
        """
        # 書き込みの前に、すべての ID を算出して入力の不正を検出する。
        document_ids = [
            compute_document_id(context.source_id, document.external_id) for document in documents
        ]
        with self._source_locks.hold(context.source_id):
            admission = self._admission_checker.check(
                source_id=context.source_id,
                crawl_id=context.crawl_id,
                crawl_started_at=context.crawl_started_at,
            )
            return self._register_all(context, admission, documents, document_ids)

    def _register_all(
        self,
        context: CrawlContext,
        admission: Admission,
        documents: Sequence[DocumentInput],
        document_ids: Sequence[str],
    ) -> list[DocumentOutcome]:
        outcomes: list[DocumentOutcome] = []
        lock_lost = False
        for document, document_id in zip(documents, document_ids, strict=True):
            # 最初の失敗以降は、確認済みの結果をそのまま返し、未処理の文書は書かずに
            # `lock_not_owned` にする(plan 案5)。ロックを失ったジョブの書き込みを止める。
            lock_lost = lock_lost or not self._ownership.is_owned(context)
            if lock_lost:
                outcomes.append(_failed(document, document_id, FailureType.LOCK_NOT_OWNED))
                continue
            outcomes.append(self._register_one(context, admission, document, document_id))
        return outcomes

    def _register_one(
        self,
        context: CrawlContext,
        admission: Admission,
        document: DocumentInput,
        document_id: str,
    ) -> DocumentOutcome:
        if self._is_oversize(document):
            return _failed(document, document_id, FailureType.OVERSIZE)
        if not _metadata_is_encodable(document):
            return _failed(
                document,
                document_id,
                FailureType.DOCUMENT_REJECTED,
                detail=_UNENCODABLE_METADATA_DETAIL,
            )
        extraction = self._extractor.extract(document.raw_content, document.mime_type)

        # 最初の読み出しに続けて、読み直しは `write_conflict_max_rereads` 回まで。
        for _ in range(self._config.write_conflict_max_rereads + 1):
            previous = self._search_index.fetch(document_id)
            outcome = self._write_once(
                context, admission, document, document_id, extraction, previous
            )
            if outcome is not None:
                return outcome
        return _failed(document, document_id, FailureType.WRITE_CONFLICT)

    def _is_oversize(self, document: DocumentInput) -> bool:
        limit = self._config.max_raw_bytes
        return document.size > limit or len(document.raw_content) > limit

    def _write_once(
        self,
        context: CrawlContext,
        admission: Admission,
        document: DocumentInput,
        document_id: str,
        extraction: ExtractionResult,
        previous: StoredDocument | None,
    ) -> DocumentOutcome | None:
        """読んだ文書に対する 1 回の判定と書き込み。None は「読み直して再判定する」。"""
        source = build_source(
            document_id=document_id,
            source_id=context.source_id,
            document=document,
            extraction=extraction,
            previous=previous.source if previous is not None else None,
            rewrite_mode=admission.rewrite_mode,
            summary_enabled=self._config.summary_enabled,
            crawl_started_at=context.crawl_started_at,
            indexed_at=self._clock.now(),
        )
        extract_failed = isinstance(extraction, ExtractionFailed)

        if previous is None:
            written = self._search_index.create(document_id, source)
            change = Change.CREATED
        elif not admission.rewrite_mode and is_unchanged(previous.source, source):
            return self._complete_last_seen_at(
                context, document, document_id, previous, extract_failed
            )
        else:
            written = self._search_index.replace_if_unchanged(
                document_id, source, seq_no=previous.seq_no, primary_term=previous.primary_term
            )
            change = Change.UPDATED

        match written:
            case Written():
                self._request_summary_if_pending(document_id, source)
                return DocumentRegistered(document.external_id, document_id, change, extract_failed)
            case Rejected(error_type=error_type):
                return _failed(
                    document, document_id, FailureType.DOCUMENT_REJECTED, detail=error_type
                )
            case Conflict() | NotFound():
                # 読んだあとに別の書き込み・削除が入った。読み直して再判定する(文書がなければ新規)。
                return None

    def _complete_last_seen_at(
        self,
        context: CrawlContext,
        document: DocumentInput,
        document_id: str,
        previous: StoredDocument,
        extract_failed: bool,
    ) -> DocumentOutcome | None:
        """(b) 変更なし。書かない。ただし `last_seen_at` が古いときだけ Update(max)で補う(K27)。

        列挙時の `last_seen_at` 部分更新が成功していれば、補完は要らない(防御的な処理)。
        """
        unchanged = DocumentRegistered(
            document.external_id, document_id, Change.UNCHANGED, extract_failed
        )
        if not last_seen_at_is_behind(previous.source, context.crawl_started_at):
            return unchanged
        match self._search_index.raise_last_seen_at(document_id, context.crawl_started_at):
            case Updated() | Unchanged():
                return unchanged
            case Conflict():
                return _failed(document, document_id, FailureType.UPDATE_CONFLICT)
            case NotFound():
                return None  # 読んだあとに文書が削除された。読み直して新規として扱う。
            case Rejected(error_type=error_type):
                # 固定のスクリプトの Update が拒否されるのは、文書ではなく Indexer 側の異常。
                raise OpenSearchUnexpectedResponseError(error_type)

    def _request_summary_if_pending(self, document_id: str, source: Mapping[str, Any]) -> None:
        """書き込みの成功後に、`pending` なら生成を依頼する。結果は待たない(M-9)。

        満杯で断られても登録は成功のまま。`pending` が残るので再走査の対象になる。
        """
        if source["summary_status"] == SummaryStatus.PENDING:
            self._summary_requests.submit(document_id)


def _metadata_is_encodable(document: DocumentInput) -> bool:
    """検索インデックスに送る文字列が UTF-8 にできる。

    孤立サロゲート(JSON の `\\ud800` など)は UTF-8 にできず、送信時の JSON 化でバッチ全体が
    落ちる。再送しても直らないため、その文書だけを拒否する。
    """
    texts = (document.title, document.mime_type, document.path, document.url)
    try:
        for text in texts:
            if text is not None:
                text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _failed(
    document: DocumentInput,
    document_id: str,
    failure_type: FailureType,
    *,
    detail: str | None = None,
) -> DocumentFailed:
    message = _FAILURE_MESSAGES[failure_type]
    if detail is not None:
        message = f"{message} ({detail})"
    return DocumentFailed(document.external_id, document_id, failure_type, message)
