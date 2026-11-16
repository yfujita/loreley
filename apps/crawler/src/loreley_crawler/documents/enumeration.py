"""列挙の包み(module 4.7。interface 3.3・5.3。architecture 4.6・7.7)。

`EnumerationStream.next()` の結果に `document_id` を付け、重複を除き、衝突を検出する。
Connector の想定外の例外は `connector_internal_error`(source)に変換する(CI-P-12)。

列挙した文書について、`document_id` と、元の `external_id`(規則適用前)の SHA-256 を持つ
(architecture CA-P-26。interface CI-U-10 への回答)。同じ `document_id` で元の値の SHA-256 が
違えば衝突で、文字列は持たないので、検出時に手元にあるのは後に来た 1 件だけになる。

失敗(列挙の `ConnectorError`・`external_id_collision`・`EnumerationTooLargeError`)は列挙の
終端で、その後の `next()` は同じ例外を再送出する(失敗の後に続きを返さない)。
"""

import hashlib
from dataclasses import dataclass

from loreley_crawler.common.display_text import format_display_text
from loreley_crawler.connectors.interface import (
    Completed,
    ConnectorError,
    DocumentRef,
    EnumerationStream,
    ErrorCategory,
    ErrorScope,
    converting_unexpected_errors,
)
from loreley_crawler.documents.document_id import compute_document_id
from loreley_crawler.documents.errors import EnumerationTooLargeError
from loreley_crawler.documents.identifiers import apply_external_id_rules
from loreley_crawler.documents.settings import DocumentsSettings


@dataclass(frozen=True)
class EnumeratedDocument:
    """規則適用後の文書参照。`ref` は `fetch` にそのまま渡す。"""

    document_id: str
    external_id: str  # Indexer に送る最終形
    ref: DocumentRef


@dataclass(frozen=True)
class InvalidExternalId:
    """`invalid_external_id` の文書。`document_id` を算出できず、登録も `last-seen` もできない。

    `display_external_id` は、規則適用前の値の表示用の文字列(孤立サロゲートの置換、制御文字の
    エスケープ、切り詰めを適用済み)。`warnings` の例に使う(architecture CA-P-25)。
    """

    error: ConnectorError
    display_external_id: str


EnumerationResult = EnumeratedDocument | InvalidExternalId | Completed


class DocumentEnumeration:
    def __init__(
        self, stream: EnumerationStream, *, source_id: str, settings: DocumentsSettings
    ) -> None:
        if "\0" in source_id:
            raise ValueError("source_id must not contain NUL")
        self._stream = stream
        self._source_id = source_id
        self._settings = settings
        # document_id -> 元の external_id(規則適用前)の SHA-256
        self._raw_digests_by_document_id: dict[str, bytes] = {}
        self._failure: Exception | None = None
        self._completed: Completed | None = None

    @property
    def enumerated_count(self) -> int:
        """列挙した文書の数。`document_id` の重複を除く(`enumerated_count`。architecture 7.5)。"""
        return len(self._raw_digests_by_document_id)

    def has_enumerated(self, document_id: str) -> bool:
        return document_id in self._raw_digests_by_document_id

    def next(self) -> EnumerationResult:
        """次の結果を返す。重複は返さず飛ばす。失敗は例外(上記の終端)。"""
        if self._failure is not None:
            raise self._failure
        if self._completed is not None:
            # 終端は 1 つ(interface 3.3 の 1)。完了の後は Connector を呼ばない。
            return self._completed
        try:
            while True:
                item = self._next_item()
                if isinstance(item, Completed):
                    self._completed = item
                    return item
                result = self._admit(item)
                if result is not None:
                    return result
        except (ConnectorError, EnumerationTooLargeError) as failure:
            self._failure = failure
            raise

    def close(self) -> None:
        """列挙だけを打ち切る(`Connector` は `fetch` に使い続けられる)。"""
        self._stream.close()

    def _next_item(self) -> DocumentRef | Completed:
        with converting_unexpected_errors(ErrorScope.SOURCE):
            item = self._stream.next()
            _check_shape(item)
            return item

    def _admit(self, ref: DocumentRef) -> EnumeratedDocument | InvalidExternalId | None:
        """重複なら None。衝突・上限超過は例外。"""
        try:
            external_id = apply_external_id_rules(ref.external_id)
        except ConnectorError as error:
            return InvalidExternalId(error, self._display(ref.external_id))

        document_id = compute_document_id(self._source_id, external_id)
        raw_digest = _digest_of_raw_external_id(ref.external_id)
        known_digest = self._raw_digests_by_document_id.get(document_id)
        if known_digest is None:
            if self.enumerated_count >= self._settings.max_enumerated_documents:
                raise EnumerationTooLargeError(self._settings.max_enumerated_documents)
            self._raw_digests_by_document_id[document_id] = raw_digest
            return EnumeratedDocument(document_id, external_id, ref)
        if known_digest == raw_digest:
            return None
        # `failure_detail` には、後に検出された 1 件の切り詰めた external_id と、共有する
        # document_id を載せる(先に来た 1 件の文字列は手元にない。architecture CA-P-45)。
        raise ConnectorError.of(
            ErrorCategory.EXTERNAL_ID_COLLISION,
            f"external_id が衝突している: `{self._display(ref.external_id)}` "
            f"(document_id={document_id})",
        )

    def _display(self, raw_external_id: str) -> str:
        return format_display_text(raw_external_id, max_chars=self._settings.display_max_chars)


def _check_shape(item: object) -> None:
    """Connector の戻り値が契約の形(`DocumentRef` か `Completed`)かを確かめる。

    形が違うものを、完了や文書と取り違えない。違反は呼び出し側で `connector_internal_error` になる。
    """
    if isinstance(item, Completed):
        return
    if not isinstance(item, DocumentRef):
        raise TypeError("enumeration must return DocumentRef or Completed")
    if not isinstance(item.external_id, str):
        raise TypeError("external_id of a DocumentRef must be a string")


def _digest_of_raw_external_id(raw_external_id: str) -> bytes:
    # 規則適用前の値は孤立サロゲートを含みうるので、`surrogatepass` で(単射に)バイト列にする。
    return hashlib.sha256(raw_external_id.encode("utf-8", "surrogatepass")).digest()
