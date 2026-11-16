"""Connector の呼び出し結果を Crawler の規則に合わせる共通処理(module 4.7)。

Indexer の `documents`(文書の登録)とは無関係。依存は `connectors` の `interface/` だけ。
"""

from loreley_crawler.documents.document_id import compute_document_id
from loreley_crawler.documents.enumeration import (
    DocumentEnumeration,
    EnumeratedDocument,
    EnumerationResult,
    InvalidExternalId,
)
from loreley_crawler.documents.errors import EnumerationTooLargeError
from loreley_crawler.documents.fetching import DocumentFetcher, PreparedDocument
from loreley_crawler.documents.identifiers import (
    MAX_EXTERNAL_ID_BYTES,
    apply_external_id_rules,
    escape_lone_surrogates_for_id,
)
from loreley_crawler.documents.settings import DocumentsSettings

__all__ = [
    "MAX_EXTERNAL_ID_BYTES",
    "DocumentEnumeration",
    "DocumentFetcher",
    "DocumentsSettings",
    "EnumeratedDocument",
    "EnumerationResult",
    "EnumerationTooLargeError",
    "InvalidExternalId",
    "PreparedDocument",
    "apply_external_id_rules",
    "compute_document_id",
    "escape_lone_surrogates_for_id",
]
