"""バッチ登録: 文書単位の結果の適用・失敗した文書だけの再送(architecture 6.2・7.3・7.7・7.11)。

Indexer の応答の扱い:
- 応答の `document_id` を、`documents` が算出した値と照合する。不一致は `CrawlFailure`
  (`document_id_mismatch`。7.11)。応答の全体を適用する前に確かめる
- `status: ok`: 結果を集計に数え(最初の結果を保持)、登録段階の連続スキップをリセットする。
  `extract_failed: true` も成功
- `document_rejected`: その文書だけを再送する(最大試行回数まで。文書ごとに数える)。尽きたら
  スキップする(`stage=index`。登録段階の連続スキップを数える)
- `oversize`: リトライせず、原本サイズ超過として記録する(計数もリセットもしない)
- `write_conflict`・`update_conflict`: その文書だけを再送する(上限付き)。解消しなければ
  `CrawlFailure`(`conflict_unresolved`)。スキップの対象にしない(確定。CA-K-10)
- `lock_not_owned`: 喪失として記録し、`OwnershipLost`(リトライもスキップもしない)
- 連続スキップの計数(`status: ok` でのリセット・スキップの加算)は、再送を終えてから、バッチの
  文書の順に反映する(再送の回の順ではなく)

リクエスト全体の失敗(500・503・接続エラー・タイムアウト)のリトライは、`IndexerCaller` がバッチ全体を
同じ内容で再送して行う。
"""

from dataclasses import dataclass

from loreley_crawler.crawl.failure import CrawlFailure
from loreley_crawler.crawl.indexer_calls import IndexerCaller
from loreley_crawler.crawl.outcomes import DocumentOutcomeRecorder
from loreley_crawler.crawl.skip_counter import ConsecutiveSkipCounter
from loreley_crawler.crawl.tally import RegistrationTally
from loreley_crawler.documents import EnumeratedDocument, PreparedDocument
from loreley_crawler.infrastructure.indexer_client import (
    BatchResults,
    DocumentFailed,
    DocumentRegistered,
    DocumentResult,
    DocumentToRegister,
    FailureType,
)
from loreley_crawler.jobs import FailureReason, OversizeDetector, SkipStage


@dataclass(frozen=True)
class PendingDocument:
    """バッチに載せる 1 件。原本(`payload.raw_content`)は、バッチの登録が終わるまで保持する。"""

    document: EnumeratedDocument
    payload: DocumentToRegister

    @classmethod
    def of(cls, document: EnumeratedDocument, prepared: PreparedDocument) -> "PendingDocument":
        metadata = prepared.metadata
        return cls(
            document,
            DocumentToRegister(
                external_id=document.external_id,
                title=metadata.title,
                mime_type=metadata.mime_type,
                raw_content=prepared.content,
                content_hash=prepared.content_hash,
                source_updated_at=metadata.source_updated_at,
                size=prepared.size,
                url=metadata.url,
                path=metadata.path,
            ),
        )

    @property
    def size(self) -> int:
        return self.payload.size


class BatchBuilder:
    """バッチの閉じ条件(文書数・原本のバイト数の合計。architecture 7.3)。"""

    def __init__(self, *, max_documents: int, max_raw_bytes: int) -> None:
        self._max_documents = max_documents
        self._max_raw_bytes = max_raw_bytes
        self._pending: list[PendingDocument] = []
        self._raw_bytes = 0

    def __len__(self) -> int:
        return len(self._pending)

    @property
    def is_full(self) -> bool:
        return len(self._pending) >= self._max_documents

    def would_exceed_bytes(self, pending: PendingDocument) -> bool:
        """加えると原本の合計が上限を超えるか。1 件も入っていなければ、常に入る(単独で送る)。"""
        return bool(self._pending) and self._raw_bytes + pending.size > self._max_raw_bytes

    def add(self, pending: PendingDocument) -> None:
        self._pending.append(pending)
        self._raw_bytes += pending.size

    def drain(self) -> list[PendingDocument]:
        pending, self._pending, self._raw_bytes = self._pending, [], 0
        return pending


@dataclass(frozen=True)
class _Registered:
    """Indexer が `status: ok` を返した。"""


@dataclass(frozen=True)
class _Oversize:
    """原本サイズ超過として記録した(連続スキップの計数に関わらない)。"""


@dataclass(frozen=True)
class _Skipped:
    """再送を尽くしても `document_rejected` だった。スキップする。"""

    attempts: int


_Settlement = _Registered | _Oversize | _Skipped


class BatchRegistrar:
    def __init__(
        self,
        *,
        indexer: IndexerCaller,
        outcomes: DocumentOutcomeRecorder,
        tally: RegistrationTally,
        skip_counter: ConsecutiveSkipCounter,
    ) -> None:
        self._indexer = indexer
        self._outcomes = outcomes
        self._tally = tally
        self._skip_counter = skip_counter

    def register(self, batch: list[PendingDocument]) -> None:
        """バッチを登録し、文書単位の結果を適用する。失敗した文書だけを、尽きるまで再送する。"""
        attempts_by_document_id: dict[str, int] = {}
        settlements: dict[str, _Settlement] = {}
        pending = batch
        resend_round = 0
        while pending:
            for item in pending:
                document_id = item.document.document_id
                attempts_by_document_id[document_id] = (
                    attempts_by_document_id.get(document_id, 0) + 1
                )
            results = self._indexer.register_documents([item.payload for item in pending])
            pending = self._apply(pending, results, attempts_by_document_id, settlements)
            if pending:
                resend_round += 1
                self._indexer.wait_before_resend(resend_round)
        self._apply_settlements_in_order(batch, settlements)

    def _apply(
        self,
        sent: list[PendingDocument],
        results: BatchResults,
        attempts_by_document_id: dict[str, int],
        settlements: dict[str, _Settlement],
    ) -> list[PendingDocument]:
        """結果を適用し、再送する文書を返す。確定した文書は `settlements` に入れる。"""
        pairs = list(zip(sent, results.documents, strict=True))
        for item, result in pairs:
            _check_document_id(item, result)
        if any(_is_lock_not_owned(result) for _item, result in pairs):
            self._indexer.raise_lock_lost()
        resend: list[PendingDocument] = []
        for item, result in pairs:
            document_id = item.document.document_id
            if isinstance(result, DocumentRegistered):
                self._tally.record_registered(result)
                settlements[document_id] = _Registered()
            elif result.failure_type is FailureType.OVERSIZE:
                self._outcomes.record_oversize(
                    item.document, detected_by=OversizeDetector.INDEXER, size=item.size
                )
                settlements[document_id] = _Oversize()
            else:
                attempts = attempts_by_document_id[document_id]
                if attempts < self._indexer.max_attempts:
                    resend.append(item)
                elif result.failure_type is FailureType.DOCUMENT_REJECTED:
                    settlements[document_id] = _Skipped(attempts)
                else:
                    # 解消しない書き込みの競合。スキップにせず、期限削除を行わせないため、
                    # ジョブを失敗にする(確定。CA-K-10)。
                    raise CrawlFailure(
                        FailureReason.CONFLICT_UNRESOLVED,
                        f"{result.failure_type.value} が解消しない",
                    )
        return resend

    def _apply_settlements_in_order(
        self, batch: list[PendingDocument], settlements: dict[str, _Settlement]
    ) -> None:
        """連続スキップの計数を、再送の回ではなくバッチの文書の順に反映する。

        再送の後にスキップが確定する文書があっても、間に `status: ok` の文書があれば、連続とは
        数えない(散在するスキップで打ち切らない。architecture 6.3)。
        """
        for item in batch:
            settlement = settlements[item.document.document_id]
            if isinstance(settlement, _Registered):
                self._skip_counter.record_success(SkipStage.INDEX)
            elif isinstance(settlement, _Skipped):
                self._outcomes.record_skip(
                    item.document,
                    stage=SkipStage.INDEX,
                    failure_name=FailureType.DOCUMENT_REJECTED.value,
                    attempts=settlement.attempts,
                )


def _check_document_id(item: PendingDocument, result: DocumentResult) -> None:
    if result.document_id != item.document.document_id:
        raise CrawlFailure(
            FailureReason.DOCUMENT_ID_MISMATCH,
            "Indexer の document_id が Crawler の算出値と一致しない"
            f"(crawler={item.document.document_id}、indexer={result.document_id})",
        )


def _is_lock_not_owned(result: DocumentResult) -> bool:
    return isinstance(result, DocumentFailed) and result.failure_type is FailureType.LOCK_NOT_OWNED
