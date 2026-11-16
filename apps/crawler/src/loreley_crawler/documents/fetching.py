"""取得の包み(module 4.7。interface 4章・5.4・7章。architecture 6.5)。

`fetch` に `max_bytes` を渡し、`size_hint` が上限を超えるときは読まずに `oversize` にする。
原本から `content_hash`・`size` を算出する(送るバイト列と同じものから算出するので、取得後に
ファイルが変わっても、ハッシュは送った内容と必ず一致する)。メタデータの孤立サロゲートは、
Indexer が文書単位の `document_rejected` にする(K59)ので、送る前に表示用に置換する。
"""

import hashlib
from dataclasses import dataclass, replace

from loreley_crawler.common.display_text import replace_lone_surrogates
from loreley_crawler.connectors.interface import (
    Connector,
    ConnectorError,
    DocumentMetadata,
    DocumentRef,
    ErrorCategory,
    ErrorScope,
    converting_unexpected_errors,
)
from loreley_crawler.documents.settings import DocumentsSettings


@dataclass(frozen=True)
class PreparedDocument:
    """Indexer のバッチ登録に載せる原本とメタデータ。

    - `content_hash`: `content` の SHA-256。小文字 16 進 64 桁
    - `size`: `content` のバイト数(0 以上)
    - `metadata`: `title`・`path`・`url`・`mime_type` の孤立サロゲートを置換済み
    """

    content: bytes
    content_hash: str
    size: int
    metadata: DocumentMetadata


class DocumentFetcher:
    def __init__(self, connector: Connector, *, settings: DocumentsSettings) -> None:
        self._connector = connector
        self._max_raw_bytes = settings.max_raw_bytes

    def fetch(self, ref: DocumentRef) -> PreparedDocument:
        """失敗は `ConnectorError`(想定外の例外は `connector_internal_error`(document))。"""
        if ref.size_hint is not None and ref.size_hint > self._max_raw_bytes:
            raise _oversize()
        # 後処理も変換の中に入れる。Connector が `content` に `str`、`title` に `None` を返すなどの
        # 不正な戻り値で、生の例外が `crawl` まで抜けないようにする。
        with converting_unexpected_errors(ErrorScope.DOCUMENT):
            fetched = self._connector.fetch(ref, self._max_raw_bytes)
            content = fetched.content
            if not isinstance(content, bytes):
                raise TypeError("fetched content must be bytes")
            if len(content) > self._max_raw_bytes:
                # Connector が上限を守らなかった場合の防御。大きな原本をバッチに載せない。
                raise _oversize()
            return PreparedDocument(
                content=content,
                content_hash=hashlib.sha256(content).hexdigest(),
                size=len(content),
                metadata=_for_display(fetched.metadata),
            )


def _oversize() -> ConnectorError:
    return ConnectorError.of(ErrorCategory.OVERSIZE, "原本が上限を超えている")


def _for_display(metadata: DocumentMetadata) -> DocumentMetadata:
    return replace(
        metadata,
        title=replace_lone_surrogates(metadata.title),
        mime_type=replace_lone_surrogates(metadata.mime_type),
        path=None if metadata.path is None else replace_lone_surrogates(metadata.path),
        url=None if metadata.url is None else replace_lone_surrogates(metadata.url),
    )
