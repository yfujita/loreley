"""形式別の本文抽出と、正規化・切り詰め・`text_hash` の計算(module 4.3)。

OpenSearch に依存しない純粋な処理。原本サイズ(`max_raw_bytes`)の超過判定は登録側が行う。
"""

from dataclasses import dataclass

from loreley_indexer.documents.extraction.decoding import decode_text
from loreley_indexer.documents.extraction.html import UnparsableHtmlError, html_to_text
from loreley_indexer.documents.extraction.normalization import (
    hash_text,
    normalize_text,
    truncate_to_utf8_bytes,
)
from loreley_indexer.documents.extraction.pdf import (
    EncryptedPdfError,
    UnreadablePdfError,
    pdf_to_text,
)
from loreley_indexer.documents.extraction.results import (
    ExtractedText,
    ExtractionFailed,
    ExtractionFailureReason,
    ExtractionResult,
)

# Markdown は記法を解釈せず、原文のまま本文にする(検索で記法の文字列も当たりうる)。
_HTML_MIME_TYPE = "text/html"
_PDF_MIME_TYPE = "application/pdf"
_DECODABLE_TEXT_MIME_TYPES = frozenset(
    {"text/plain", "text/markdown", "text/x-markdown", _HTML_MIME_TYPE}
)


@dataclass(frozen=True)
class ExtractionConfig:
    max_content_bytes: int  # 抽出・正規化後の本文の上限(UTF-8 のバイト数)。arch 15.2

    def __post_init__(self) -> None:
        if self.max_content_bytes < 1:
            raise ValueError("max_content_bytes must be at least 1")


class TextExtractor:
    def __init__(self, config: ExtractionConfig) -> None:
        self._max_content_bytes = config.max_content_bytes

    def extract(self, raw_content: bytes, mime_type: str) -> ExtractionResult:
        """原本から本文を取り出し、正規化して上限で切り詰める。失敗は例外でなく結果で返す。"""
        raw_text = self._extract_raw_text(raw_content, _base_mime_type(mime_type))
        if isinstance(raw_text, ExtractionFailed):
            return raw_text
        text, truncated = truncate_to_utf8_bytes(normalize_text(raw_text), self._max_content_bytes)
        return ExtractedText(text=text, truncated=truncated, text_hash=hash_text(text))

    def _extract_raw_text(self, raw_content: bytes, base_mime_type: str) -> str | ExtractionFailed:
        if base_mime_type == _PDF_MIME_TYPE:
            return self._extract_pdf(raw_content)
        if base_mime_type not in _DECODABLE_TEXT_MIME_TYPES:
            return ExtractionFailed(ExtractionFailureReason.UNSUPPORTED_MIME_TYPE)
        decoded = decode_text(raw_content)
        if decoded is None:
            return ExtractionFailed(ExtractionFailureReason.UNDECODABLE_TEXT)
        if base_mime_type == _HTML_MIME_TYPE:
            return _extract_html(decoded)
        return decoded

    def _extract_pdf(self, raw_content: bytes) -> str | ExtractionFailed:
        try:
            return pdf_to_text(raw_content, self._max_content_bytes)
        except EncryptedPdfError:
            return ExtractionFailed(ExtractionFailureReason.ENCRYPTED_PDF)
        except UnreadablePdfError:
            return ExtractionFailed(ExtractionFailureReason.CORRUPT_DOCUMENT)


def _base_mime_type(mime_type: str) -> str:
    """`text/html; charset=utf-8` のパラメータを除き、小文字にする。"""
    return mime_type.split(";", 1)[0].strip().lower()


def _extract_html(html: str) -> str | ExtractionFailed:
    try:
        return html_to_text(html)
    except UnparsableHtmlError:
        return ExtractionFailed(ExtractionFailureReason.CORRUPT_DOCUMENT)
